import os
import uuid
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


def _parse_cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw:
        return ["*"]
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins or ["*"]


def _minio_bucket() -> str:
    return (os.getenv("MINIO_BUCKET") or os.getenv("MINIO_BUCKET_NAME") or "products").strip()


app = FastAPI(title="Clothing API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(looks_router)
app.include_router(wear_log_router)

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
                # миграции могли ещё не примениться — не падаем
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


@app.get("/health", operation_id="health")
def health():
    return {"status": "ok"}


class UploadResp(BaseModel):
    id: str
    bucket: str
    object_key: str
    url: str
    content_type: str | None = None


def guess_ext(filename: str | None) -> str | None:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in ("jpg", "jpeg", "png", "webp"):
        return "jpg" if ext == "jpeg" else ext
    return None


@app.post("/v1/media/upload", response_model=UploadResp, operation_id="upload_media")
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image/* is allowed")

    bucket = _minio_bucket()

    ext = guess_ext(file.filename) or "jpg"
    object_key = f"{current.id}/{uuid.uuid4()}.{ext}"

    data = await file.read()
    put_object(bucket=bucket, key=object_key, data=data, content_type=file.content_type)

    media_id = str(uuid.uuid4())
    m_kwargs = dict(
        id=media_id,
        owner_id=current.id,
        bucket=bucket,
        object_key=object_key,
        content_type=file.content_type,
    )
    if hasattr(Media, "created_at"):
        m_kwargs["created_at"] = datetime.utcnow()

    db.add(Media(**m_kwargs))
    db.commit()

    return UploadResp(
        id=media_id,
        bucket=bucket,
        object_key=object_key,
        url=f"/media/{bucket}/{object_key}",
        content_type=file.content_type,
    )


class CreateJobReq(BaseModel):
    media_id: str
    hint: dict[str, Any] | None = None


class CreateJobResp(BaseModel):
    job_id: str
    status: str


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


@app.get("/v1/categories/tree", operation_id="categories_tree")
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
    title: str | None = None
    description: str | None = None
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None


class ProductPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: str | None = None


class AttachMediaReq(BaseModel):
    media_id: str
    kind: str = "original"  # original|processed


@app.post("/v1/products", operation_id="create_product")
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    now = datetime.utcnow()

    title = (payload.title or "Новый товар").strip()
    description = (payload.description or "").strip()

    p_kwargs = dict(
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

    # обновляем поисковый индекс гардероба
    try:
        enqueue_index_product(p.id)
    except Exception:
        pass

    return {"id": p.id, "status": p.status}


@app.get("/v1/products", operation_id="list_products")
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


@app.post("/v1/products/{product_id}/media", operation_id="attach_media")
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

    pm_kwargs = dict(
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

    # чтобы сортировка/поиск учитывали прикрепление медиа
    if hasattr(p, "updated_at"):
        p.updated_at = datetime.utcnow()

    db.commit()

    # обновляем поисковый индекс гардероба
    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok", "id": pm.id}


@app.get("/v1/products/{product_id}", operation_id="get_product")
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


@app.patch("/v1/products/{product_id}", operation_id="patch_product")
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

    # обновляем поисковый индекс гардероба
    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok"}


@app.post("/v1/products/{product_id}/publish", operation_id="publish_product")
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

    # обновляем поисковый индекс гардероба
    try:
        enqueue_index_product(product_id)
    except Exception:
        pass

    return {"status": "ok", "product_id": product_id}