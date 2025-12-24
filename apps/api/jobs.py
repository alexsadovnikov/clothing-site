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

        # ВАЖНО: выносим из ORM-объекта в простые значения
        bucket = media.bucket
        object_key = media.object_key
        content_type = media.content_type
        hint = job.hint

    # 2) Вызываем AI сервис (обязательно с timeout)
    ai_url = os.getenv("AI_INTERNAL_URL", "http://ai:8002")
    try:
        resp = requests.post(
            f"{ai_url}/v1/analyze",
            json={"bucket": bucket, "object_key": object_key, "hint": hint},
            timeout=(5, 60),  # 5s connect, 60s response
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
    title = result.get("title_suggested") or "Товар (черновик)"
    category_id = result.get("category_id")  # может быть None
    attributes = result.get("attributes") or {}
    tags = result.get("tags") or []

    with SessionLocal() as db:
        try:
            p = Product(
                id=product_id,
                status="draft",
                title=title,
                description=result.get("description_draft"),
                category_id=category_id,
                attributes=attributes,
                tags=tags,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(p)

            # КЛЮЧЕВОЕ: форсируем INSERT продукта ДО того, как обновим ai_jobs.draft_product_id
            db.flush()

            pm = ProductMedia(
                id=str(uuid.uuid4()),
                product_id=product_id,
                bucket=bucket,
                object_key=object_key,
                kind="original",
                content_type=content_type,
            )
            db.add(pm)

            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if not job:
                # крайне редкий случай: job исчез
                db.rollback()
                return

            job.status = "done"
            job.result_json = result
            job.draft_product_id = product_id
            job.updated_at = datetime.utcnow()

            db.commit()

        except Exception as e:
            db.rollback()
            # обязательно помечаем job как error, иначе будет вечный processing
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

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            return

        doc = {
            "id": p.id,
            "status": p.status,
            "title": p.title,
            "description": p.description,
            "category_id": p.category_id,
            "attributes": p.attributes,
            "tags": p.tags,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

    client.index(index_name).add_documents([doc])