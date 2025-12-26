import os
import uuid
from datetime import datetime
from typing import Any

import requests
from meilisearch import Client as MeiliClient

from db import SessionLocal
from models import AIJob, Media, Product, ProductMedia


def process_ai_job(job_id: str):
    # 1) Берём job + media и сохраняем нужные поля в простые переменные
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.utcnow()
        db.commit()

        media = db.query(Media).filter(Media.id == job.media_id).first()
        if not media:
            job.status = "error"
            job.error = "Media not found"
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        owner_id = job.owner_id
        bucket = media.bucket
        object_key = media.object_key
        content_type = getattr(media, "content_type", None)
        hint = job.hint

    # 2) Вызываем AI сервис (обязательно с timeout)
    ai_url = os.getenv("AI_INTERNAL_URL", "http://ai:8002")
    try:
        resp = requests.post(
            f"{ai_url}/v1/analyze",
            json={"bucket": bucket, "object_key": object_key, "hint": hint},
            timeout=(5, 60),
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
    except Exception as e:
        with SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if job:
                job.status = "error"
                job.error = f"AI request failed: {e}"
                job.updated_at = datetime.utcnow()
                db.commit()
        return

    # 3) Создаём draft product + media + обновляем job (в одной транзакции)
    product_id = str(uuid.uuid4())
    title = (result.get("title_suggested") or "Товар (черновик)").strip()
    category_id = result.get("category_id")  # может быть None
    attributes = result.get("attributes") or {}
    tags = result.get("tags") or []

    with SessionLocal() as db:
        try:
            now = datetime.utcnow()

            p_kwargs = dict(
                id=product_id,
                owner_id=owner_id,          # ✅ КЛЮЧЕВОЕ
                status="draft",
                title=title,
                description=(result.get("description_draft") or ""),
                category_id=category_id,
                attributes=attributes,
                tags=tags,
            )
            if hasattr(Product, "created_at"):
                p_kwargs["created_at"] = now
            if hasattr(Product, "updated_at"):
                p_kwargs["updated_at"] = now

            p = Product(**p_kwargs)
            db.add(p)
            db.flush()  # форсим INSERT

            pm_kwargs = dict(
                id=str(uuid.uuid4()),
                product_id=product_id,
                bucket=bucket,
                object_key=object_key,
                kind="original",
            )
            # ⚠️ эти поля могут/не могут быть в модели — делаем безопасно
            if hasattr(ProductMedia, "content_type") and content_type:
                pm_kwargs["content_type"] = content_type
            if hasattr(ProductMedia, "created_at"):
                pm_kwargs["created_at"] = now

            db.add(ProductMedia(**pm_kwargs))

            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if not job:
                db.rollback()
                return

            job.status = "done"
            job.result_json = result
            job.draft_product_id = product_id
            job.updated_at = now
            db.commit()

        except Exception as e:
            db.rollback()
            try:
                job = db.query(AIJob).filter(AIJob.id == job_id).first()
                if job:
                    job.status = "error"
                    job.error = f"DB commit failed: {e}"
                    job.updated_at = datetime.utcnow()
                    db.commit()
            except Exception:
                db.rollback()
            return


def index_product(product_id: str):
    meili_host = os.getenv("MEILI_HOST")
    meili_key = os.getenv("MEILI_MASTER_KEY")
    index_name = os.getenv("MEILI_INDEX", "products")
    if not meili_host or not meili_key:
        return

    client = MeiliClient(meili_host, meili_key)
    idx = client.index(index_name)

    # один раз выставим настройки (чтобы фильтры работали)
    try:
        idx.update_filterable_attributes(["status", "owner_id", "category_id", "tags"])
        idx.update_sortable_attributes(["updated_at"])
    except Exception:
        pass

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            return

        # ВАЖНО ДЛЯ ГАРДЕРОБА:
        # НЕ режем по published, потому что AI создаёт draft, а поиск нужен по всему гардеробу.
        # Если вдруг хочешь индексировать только published — верни эту проверку обратно.
        # if getattr(p, "status", None) != "published":
        #     return

        media_rows = db.query(ProductMedia).filter(ProductMedia.product_id == p.id).all()

        doc = {
            "id": p.id,
            "owner_id": p.owner_id,
            "status": p.status,
            "title": p.title,
            "description": p.description,
            "category_id": p.category_id,
            "attributes": p.attributes or {},
            "tags": p.tags or [],
            "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
            "media": [
                {
                    "bucket": m.bucket,
                    "object_key": m.object_key,
                    "kind": m.kind,
                    "url": f"/media/{m.bucket}/{m.object_key}",
                }
                for m in media_rows
            ],
        }

    try:
        idx.add_documents([doc])
    except Exception:
        pass