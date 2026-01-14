import os
import uuid
import time
import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, AnyUrl
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from db import get_db, SessionLocal
from storage import ensure_bucket, put_object
from models import Category, Media, AIJob, Product, ProductMedia, User
from queueing import enqueue_process_job, enqueue_index_product
from search_routes import router as catalog_router
from looks_routes import router as looks_router
from wear_log_routes import router as wear_log_router
from auth import router as auth_router, get_current_user  # type: ignore

logger = logging.getLogger(__name__)

API_VERSION = os.getenv("API_VERSION", "1").strip() or "1"

ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}

MAX_UPLOAD_BYTES = int(os.getenv("MAX_FILE_SIZE", str(10 * 1024 * 1024)))  # 10MB
FORCE_WEBP = os.getenv("FORCE_WEBP", "0").strip() == "1"


def _cors_kwargs() -> dict:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    allow_credentials_env = (os.getenv("ALLOW_CREDENTIALS") or "0").strip() == "1"

    if raw == "*":
        origins = ["*"]
    elif raw:
        origins = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
    else:
        origins = ["https://voicecrm.online"]

    allow_credentials = bool(allow_credentials_env and origins != ["*"])

    return {
        "allow_origins": origins,
        "allow_origin_regex": r"^https?://([a-z0-9-]+\.)*(localhost|127\.0\.0\.1)(:\d+)?$",
        "allow_credentials": allow_credentials,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def _minio_bucket() -> str:
    # bucket только из env сервиса (не из user input)
    return (os.getenv("MINIO_BUCKET") or os.getenv("MINIO_BUCKET_NAME") or "products").strip()


app = FastAPI(title="Clothing API", version="0.1.0")

app.add_middleware(CORSMiddleware, **_cors_kwargs())

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(looks_router)
app.include_router(wear_log_router)


# ---------- унификация ошибок (всегда JSON) ----------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        "HTTPException status=%s path=%s method=%s detail=%s ip=%s ua=%s",
        exc.status_code,
        request.url.path,
        request.method,
        exc.detail,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "detail": exc.detail},
        headers={"API-Version": API_VERSION},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled error path=%s method=%s ip=%s ua=%s",
        request.url.path,
        request.method,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Internal Server Error"},
        headers={"API-Version": API_VERSION},
    )


# ---------- middleware: Vary + timing + api-version ----------

@app.middleware("http")
async def add_headers_and_timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)

    origin = request.headers.get("origin")
    if origin:
        vary = response.headers.get("Vary")
        if vary:
            if "Origin" not in vary:
                response.headers["Vary"] = f"{vary}, Origin"
        else:
            response.headers["Vary"] = "Origin"

    response.headers["API-Version"] = API_VERSION
    response.headers["X-Response-Time-ms"] = str(int((time.perf_counter() - t0) * 1000))
    return response


@app.on_event("startup")
def _startup():
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning("ensure_bucket failed on startup (minio not ready?): %s", e)

    try:
        with SessionLocal() as db:
            try:
                db.execute(text("SELECT 1 FROM categories LIMIT 1"))
            except (OperationalError, ProgrammingError):
                return

            count = db.query(Category).count()
            if count == 0:
                seed_categories(db)
    except Exception as e:
        logger.warning("startup seeding failed: %s", e)


def seed_categories(db: Session) -> None:
    root_defs = [
        ("odezhda", "Одежда"),
        ("obuv", "Обувь"),
        ("aksessuary", "Аксессуары"),
    ]
    roots: dict[str, Category] = {}

    for slug, name in root_defs:
        c = Category(
            id=str(uuid.uuid4()),
            parent_id=None,
            name=name,
            slug=slug,
            path=slug,
            sort_order=0,
            is_active=True,
            ai_aliases={},
        )
        db.add(c)
        roots[slug] = c

    db.flush()

    sub_defs = [
        ("odezhda", "futbolki", "Футболки"),
        ("odezhda", "dzhinsy", "Джинсы"),
        ("obuv", "krossovki", "Кроссовки"),
        ("aksessuary", "sumki", "Сумки"),
    ]

    for root_slug, slug, name in sub_defs:
        parent = roots[root_slug]
        c = Category(
            id=str(uuid.uuid4()),
            parent_id=parent.id,
            name=name,
            slug=slug,
            path=f"{parent.path}/{slug}",
            sort_order=0,
            is_active=True,
            ai_aliases={},
        )
        db.add(c)

    db.commit()


def guess_ext(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in ALLOWED_IMAGE_EXTS:
        return ext
    return None


def sniff_image_mime(data: bytes) -> tuple[str | None, str | None]:
    if len(data) >= 3 and data[:3] == b"\xFF\xD8\xFF":
        return "image/jpeg", "jpg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None, None


def pil_verify_image(data: bytes) -> None:
    try:
        from io import BytesIO
        from PIL import Image  # type: ignore
    except Exception:
        # Pillow не установлен — просто пропускаем
        return

    try:
        img = Image.open(BytesIO(data))
        img.verify()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid image content: {e}")


def maybe_convert_to_webp(data: bytes) -> tuple[bytes, str, str]:
    """
    Если FORCE_WEBP=1 — пытаемся конвертить в webp.
    ВАЖНО: если webp encoder недоступен (часто бывает) — НЕ падаем, а возвращаем оригинал.
    """
    sniff_mime, sniff_ext = sniff_image_mime(data)
    if not sniff_mime or not sniff_ext:
        return data, "application/octet-stream", "bin"

    # если не форсим webp — оставляем как есть
    if not FORCE_WEBP:
        return data, sniff_mime, sniff_ext

    # уже webp — оставляем
    if sniff_mime == "image/webp":
        return data, "image/webp", "webp"

    try:
        from io import BytesIO
        from PIL import Image  # type: ignore

        img = Image.open(BytesIO(data))
        out = BytesIO()
        img.save(out, format="WEBP", quality=85, method=6)
        return out.getvalue(), "image/webp", "webp"
    except Exception as e:
        # критично: не даём 500 — просто используем оригинальный файл
        logger.warning("webp conversion skipped (fallback to original). err=%s", e)
        return data, sniff_mime, sniff_ext


def put_object_with_retry(object_key: str, data: bytes, content_type: str, retries: int = 3) -> None:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            put_object(object_key=object_key, data=data, content_type=content_type)
            return
        except Exception as e:
            last_err = e
            logger.warning("put_object failed attempt=%s/%s key=%s err=%s", attempt, retries, object_key, e)
            time.sleep(0.2 * attempt)
    raise HTTPException(status_code=503, detail=f"storage unavailable: {last_err}")


@app.get("/health", operation_id="health", response_model=dict)
def health():
    return {"status": "ok"}


class UploadResp(BaseModel):
    id: str = Field(..., description="ID медиа-объекта (UUID)")
    bucket: str = Field(..., description="Имя bucket в хранилище")
    object_key: str = Field(..., description="Ключ объекта в bucket")
    url: AnyUrl = Field(..., description="Абсолютный URL доступа к медиа")
    content_type: str | None = Field(None, description="MIME тип файла")


@app.post("/v1/media/upload", response_model=UploadResp, operation_id="upload_media")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    t0 = time.perf_counter()

    ext_from_name = guess_ext(file.filename)
    if not ext_from_name:
        raise HTTPException(status_code=400, detail="only jpg/jpeg/png/webp files are allowed")

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image/* is allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"file too large (max {MAX_UPLOAD_BYTES} bytes)")

    sniff_mime, sniff_ext = sniff_image_mime(data)
    if not sniff_mime or sniff_mime not in ALLOWED_IMAGE_MIME:
        raise HTTPException(status_code=400, detail="invalid image mime by content")

    pil_verify_image(data)

    data2, final_mime, final_ext = maybe_convert_to_webp(data)
    if final_mime not in ALLOWED_IMAGE_MIME:
        raise HTTPException(status_code=400, detail="unsupported image after processing")

    bucket = _minio_bucket()
    object_key = f"{current.id}/{uuid.uuid4()}.{final_ext}"

    checksum = hashlib.sha256(data2).hexdigest()
    size_bytes = len(data2)

    put_object_with_retry(object_key=object_key, data=data2, content_type=final_mime)

    media_id = str(uuid.uuid4())
    m_kwargs: dict[str, Any] = dict(
        id=media_id,
        owner_id=current.id,
        bucket=bucket,
        object_key=object_key,
        content_type=final_mime,
    )

    if hasattr(Media, "created_at"):
        m_kwargs["created_at"] = datetime.utcnow()
    if hasattr(Media, "size_bytes"):
        m_kwargs["size_bytes"] = size_bytes
    if hasattr(Media, "checksum_sha256"):
        m_kwargs["checksum_sha256"] = checksum

    db.add(Media(**m_kwargs))
    db.commit()

    base = str(request.base_url).rstrip("/")
    url = f"{base}/media/{bucket}/{object_key}"

    logger.info(
        "media_upload ok user=%s media_id=%s bytes=%s mime=%s ms=%s",
        current.id,
        media_id,
        size_bytes,
        final_mime,
        int((time.perf_counter() - t0) * 1000),
    )

    return UploadResp(
        id=media_id,
        bucket=bucket,
        object_key=object_key,
        url=url,
        content_type=final_mime,
    )


class CreateJobReq(BaseModel):
    media_id: str = Field(..., description="ID загруженного медиа")
    hint: dict[str, Any] | None = Field(
        default=None,
        description="Подсказки для AI (JSON). Структура зависит от версии модели.",
        examples=[{"category_hint": "odezhda/futbolki"}],
    )


class CreateJobResp(BaseModel):
    job_id: str = Field(..., description="ID задачи AI")
    status: str = Field(..., description="Статус (queued/processing/done/error)")


@app.post("/v1/ai/jobs", response_model=CreateJobResp, operation_id="create_ai_job")
def create_ai_job(
    payload: CreateJobReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == payload.media_id).first()
    if not media or media.owner_id != current.id:
        raise HTTPException(status_code=404, detail="media_id not found")

    job_id = str(uuid.uuid4())
    now = datetime.utcnow()

    db.add(
        AIJob(
            id=job_id,
            owner_id=current.id,
            status="queued",
            media_id=media.id,
            hint=payload.hint or {},
            result_json=None,
            error=None,
            model_version="stub-v1",
            draft_product_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()

    enqueue_process_job(job_id)
    return CreateJobResp(job_id=job_id, status="queued")


class JobResp(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    draft_product_id: str | None = None


@app.get("/v1/ai/jobs/{job_id}", response_model=JobResp, operation_id="get_ai_job")
def get_ai_job(
    job_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    job = db.query(AIJob).filter(AIJob.id == job_id).first()
    if not job or job.owner_id != current.id:
        raise HTTPException(status_code=404, detail="job not found")

    return JobResp(
        job_id=job.id,
        status=job.status,
        result=job.result_json,
        error=job.error,
        draft_product_id=job.draft_product_id,
    )


@app.get("/v1/categories/tree", operation_id="categories_tree", response_model=dict)
def categories_tree(db: Session = Depends(get_db)):
    cats = db.query(Category).all()
    nodes = {
        c.id: {"id": c.id, "name": c.name, "slug": c.slug, "path": c.path, "children": []}
        for c in cats
    }
    root = []
    for c in cats:
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id]["children"].append(nodes[c.id])
        else:
            root.append(nodes[c.id])
    return {"items": root}


class ProductCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=10000)
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None


class ProductPatch(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=10000)
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: str | None = None


class AttachMediaReq(BaseModel):
    media_id: str
    kind: str = Field("original", description="original|processed")


@app.post("/v1/products", operation_id="create_product", response_model=dict)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    now = datetime.utcnow()

    title = (payload.title or "Новый товар").strip()
    description = (payload.description or "").strip()

    p_kwargs: dict[str, Any] = dict(
        id=str(uuid.uuid4()),
        owner_id=current.id,
        status="draft",
        title=title,
        description=description,
        category_id=payload.category_id,
        attributes=payload.attributes or {},
        tags=payload.tags or [],
    )
    if hasattr(Product, "created_at"):
        p_kwargs["created_at"] = now
    if hasattr(Product, "updated_at"):
        p_kwargs["updated_at"] = now

    p = Product(**p_kwargs)
    db.add(p)
    db.commit()

    try:
        enqueue_index_product(p.id)
    except Exception:
        pass

    return {"id": p.id, "status": p.status}


@app.get("/v1/products", operation_id="list_products", response_model=dict)
def list_products(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    q = db.query(Product).filter(Product.owner_id == current.id)
    if status:
        q = q.filter(Product.status == status)

    total = q.count()

    if hasattr(Product, "updated_at"):
        q = q.order_by(Product.updated_at.desc().nullslast(), Product.created_at.desc().nullslast())
    else:
        q = q.order_by(Product.created_at.desc().nullslast())

    items = q.limit(limit).offset(offset).all()

    return {
        "items": [
            {
                "id": p.id,
                "status": p.status,
                "title": p.title,
                "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
                "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
            }
            for p in items
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@app.post("/v1/products/{product_id}/media", operation_id="attach_media", response_model=dict)
def attach_media_to_product(
    product_id: str,
    payload: AttachMediaReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if payload.kind not in ("original", "processed"):
        raise HTTPException(status_code=400, detail="kind must be original|processed")

    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    m = db.query(Media).filter(Media.id == payload.media_id).first()
    if not m or m.owner_id != current.id:
        raise HTTPException(status_code=404, detail="media not found")

    existing = (
        db.query(ProductMedia)
        .filter(
            ProductMedia.product_id == p.id,
            ProductMedia.bucket == m.bucket,
            ProductMedia.object_key == m.object_key,
            ProductMedia.kind == payload.kind,
        )
        .first()
    )
    if existing:
        return {"status": "ok", "id": existing.id}

    pm_kwargs: dict[str, Any] = dict(
        id=str(uuid.uuid4()),
        product_id=p.id,
        bucket=m.bucket,
        object_key=m.object_key,
        kind=payload.kind,
    )
    if hasattr(ProductMedia, "content_type"):
        pm_kwargs["content_type"] = getattr(m, "content_type", None)
    if hasattr(ProductMedia, "created_at"):
        pm_kwargs["created_at"] = datetime.utcnow()

    pm = ProductMedia(**pm_kwargs)
    db.add(pm)

    if hasattr(p, "updated_at"):
        p.updated_at = datetime.utcnow()

    db.commit()

    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok", "id": pm.id}


@app.get("/v1/products/{product_id}", operation_id="get_product", response_model=dict)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    media_rows = db.query(ProductMedia).filter(ProductMedia.product_id == p.id).all()

    return {
        "id": p.id,
        "status": p.status,
        "title": p.title,
        "description": p.description,
        "category_id": p.category_id,
        "attributes": p.attributes or {},
        "tags": p.tags or [],
        "media": [
            {"id": m.id, "url": f"/media/{m.bucket}/{m.object_key}", "kind": m.kind}
            for m in media_rows
        ],
        "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
        "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
    }


@app.patch("/v1/products/{product_id}", operation_id="patch_product", response_model=dict)
def patch_product(
    product_id: str,
    patch: ProductPatch,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    if patch.title is not None:
        p.title = patch.title
    if patch.description is not None:
        p.description = patch.description
    if patch.category_id is not None:
        p.category_id = patch.category_id
    if patch.attributes is not None:
        p.attributes = patch.attributes
    if patch.tags is not None:
        p.tags = patch.tags
    if patch.status is not None:
        p.status = patch.status

    if hasattr(p, "updated_at"):
        p.updated_at = datetime.utcnow()

    db.commit()

    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok"}


@app.post("/v1/products/{product_id}/publish", operation_id="publish_product", response_model=dict)
def publish_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    p.status = "published"
    if hasattr(p, "updated_at"):
        p.updated_at = datetime.utcnow()
    db.commit()

    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok", "product_id": product_id}