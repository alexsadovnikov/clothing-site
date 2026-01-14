import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional, Tuple

import requests
from meilisearch import Client as MeiliClient

from db import SessionLocal
from models import AIJob, Media, Product, ProductMedia


# --- Meili config ------------------------------------------------------------

_MEILI_FILTERABLE = ["status", "owner_id", "category_id", "tags"]
_MEILI_SORTABLE = ["updated_at"]


def _meili_cfg() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host = os.getenv("MEILI_HOST")
    key = os.getenv("MEILI_MASTER_KEY")
    index_name = os.getenv("MEILI_INDEX", "products")
    if not host or not key:
        return None, None, None
    return host, key, index_name


def _task_uid(task_info) -> Optional[int]:
    """
    meilisearch-python в разных версиях возвращает:
      - dict {taskUid: 12} или {uid: 12}
      - объект TaskInfo с полями .task_uid / .uid
    Нам нужен int task_uid.
    """
    if task_info is None:
        return None

    # TaskInfo object
    for attr in ("task_uid", "taskUid", "uid"):
        if hasattr(task_info, attr):
            v = getattr(task_info, attr)
            if v is not None:
                try:
                    return int(v)
                except Exception:
                    pass

    # dict
    if isinstance(task_info, dict):
        for k in ("taskUid", "uid", "task_uid"):
            if k in task_info and task_info[k] is not None:
                try:
                    return int(task_info[k])
                except Exception:
                    pass

    return None


def _wait_task(client: MeiliClient, task_uid: int, timeout_s: int = 30) -> bool:
    """
    Ждём, пока Meili применит index/settings.
    Если не дождались — вернём False (не критично для старта воркера).
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            t = client.get_task(task_uid)
            status = t.get("status") if isinstance(t, dict) else getattr(t, "status", None)
            if status in ("succeeded", "failed", "canceled"):
                return status == "succeeded"
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _index_exists(client: MeiliClient, index_name: str) -> bool:
    # 1) client.get_index(uid)
    if hasattr(client, "get_index"):
        try:
            client.get_index(index_name)
            return True
        except Exception:
            return False

    # 2) client.get_indexes()
    if hasattr(client, "get_indexes"):
        try:
            data = client.get_indexes()
            if isinstance(data, dict) and "results" in data:
                return any(
                    isinstance(x, dict) and x.get("uid") == index_name
                    for x in data.get("results", [])
                )
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, dict) and x.get("uid") == index_name:
                        return True
                    if hasattr(x, "uid") and getattr(x, "uid") == index_name:
                        return True
            return False
        except Exception:
            return False

    return False


def _get_index_info(client: MeiliClient, index_name: str) -> Optional[dict]:
    # prefer client.get_index
    if hasattr(client, "get_index"):
        try:
            info = client.get_index(index_name)
            if isinstance(info, dict):
                return info
            if hasattr(info, "__dict__"):
                # ВАЖНО: тут могут быть не-JSON объекты (config/http/task_handler),
                # но нам важны uid/primary_key/created_at/updated_at.
                return dict(info.__dict__)
        except Exception:
            pass

    idx = client.index(index_name)
    for m in ("get_raw_info", "get_info"):
        if hasattr(idx, m):
            try:
                res = getattr(idx, m)()
                if isinstance(res, dict):
                    return res
                if hasattr(res, "__dict__"):
                    return dict(res.__dict__)
            except Exception:
                pass
    return None


def _safe_pk_from_info(info: Optional[dict]) -> Optional[str]:
    """
    Meili REST: primaryKey
    meilisearch-python (некоторые версии): primary_key
    """
    if not info or not isinstance(info, dict):
        return None
    pk = info.get("primaryKey") or info.get("primary_key") or info.get("primarykey")
    if pk is None:
        return None
    try:
        return str(pk)
    except Exception:
        return None


def _safe_settings(idx) -> dict:
    """
    Возвращает settings как dict, если библиотека это умеет.
    """
    if hasattr(idx, "get_settings"):
        try:
            s = idx.get_settings()
            return s if isinstance(s, dict) else {}
        except Exception:
            return {}
    return {}


def init_meili() -> None:
    """
    Вызывается при старте воркера.
    1) гарантирует индекс (НЕ спамим create_index, если уже существует)
    2) проверяет primaryKey
    3) применяет settings ТОЛЬКО если отличаются
    """
    host, key, index_name = _meili_cfg()
    if not host or not key or not index_name:
        print("[meili:init] skipped: MEILI_HOST/MEILI_MASTER_KEY not set", flush=True)
        return

    client = MeiliClient(host, key)
    exists = _index_exists(client, index_name)

    # 1) создать индекс только если его нет
    if not exists:
        try:
            t = client.create_index(index_name, {"primaryKey": "id"})
            tuid = _task_uid(t)
            if tuid:
                _wait_task(client, tuid)
            print(f"[meili:init] created index={index_name} with primaryKey=id", flush=True)
            exists = True
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg:
                print(f"[meili:init] index={index_name} already exists (race), continue", flush=True)
                exists = True
            else:
                print(f"[meili:init] FAILED to create index={index_name}: {e}", flush=True)
                return
    else:
        print(f"[meili:init] index={index_name} exists", flush=True)

    idx = client.index(index_name)

    # 2) primaryKey: просто корректно читаем и логируем (не ломаем запуск)
    try:
        info = _get_index_info(client, index_name) or {}
        pk = _safe_pk_from_info(info)

        if not pk:
            # Никаких ложных PATCH: это часто артефакт библиотеки, PK при этом есть в REST.
            print(f"[meili:init] primaryKey unknown via client lib (info keys: {list(info.keys())}); continue", flush=True)
        elif pk != "id":
            print(f"[meili:init] WARNING: index={index_name} primaryKey={pk} (expected id)", flush=True)
        else:
            print(f"[meili:init] primaryKey OK: {pk}", flush=True)

    except Exception as e:
        print(f"[meili:init] primaryKey check skipped/failed: {e}", flush=True)

    # 3) settings: применять только если реально отличаются
    try:
        current = _safe_settings(idx)

        cur_filter = current.get("filterableAttributes") or current.get("filterable_attributes") or []
        cur_sort = current.get("sortableAttributes") or current.get("sortable_attributes") or []

        def _norm(x):
            return sorted([str(i) for i in (x or [])])

        need_filter = _norm(cur_filter) != _norm(_MEILI_FILTERABLE)
        need_sort = _norm(cur_sort) != _norm(_MEILI_SORTABLE)

        tuids = []

        if need_filter:
            t1 = idx.update_filterable_attributes(_MEILI_FILTERABLE)
            tuid1 = _task_uid(t1)
            if tuid1:
                tuids.append(tuid1)

        if need_sort:
            t2 = idx.update_sortable_attributes(_MEILI_SORTABLE)
            tuid2 = _task_uid(t2)
            if tuid2:
                tuids.append(tuid2)

        for tu in tuids:
            _wait_task(client, tu)

        if need_filter or need_sort:
            print(f"[meili:init] settings applied for index={index_name}", flush=True)
        else:
            print(f"[meili:init] settings already up-to-date for index={index_name}", flush=True)

    except Exception as e:
        print(f"[meili:init] settings apply skipped/failed: {e}", flush=True)


# --- Jobs --------------------------------------------------------------------

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
                owner_id=owner_id,  # ✅ ключевое
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
            db.flush()

            pm_kwargs = dict(
                id=str(uuid.uuid4()),
                product_id=product_id,
                bucket=bucket,
                object_key=object_key,
                kind="original",
            )
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
    """
    Runtime-индексация: только add_documents(), без PK/settings.
    Все настройки должны быть сделаны init_meili() при старте воркера.
    """
    host, key, index_name = _meili_cfg()
    if not host or not key or not index_name:
        return

    client = MeiliClient(host, key)
    idx = client.index(index_name)

    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            return

        media_rows = db.query(ProductMedia).filter(ProductMedia.product_id == p.id).all()

        doc = {
            "id": str(p.id),
            "owner_id": str(p.owner_id) if p.owner_id else None,
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
    except Exception as e:
        print(f"[meili:index] failed for product_id={product_id}: {e}", flush=True)