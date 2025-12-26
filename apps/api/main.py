import os
import uuid
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from db import get_db, SessionLocal  # ✅ ВАЖНО: вернуть get_db и SessionLocal
from storage import ensure_bucket, put_object
from models import Category, Media, AIJob, Product, ProductMedia, User
from queueing import enqueue_process_job, enqueue_index_product
from search_routes import router as catalog_router

# ✅ Роуты авторизации должны быть в apps/api/auth.py
from auth import router as auth_router, get_current_user  # type: ignore

logger = logging.getLogger(__name__)


def _parse_cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw:
        return ["*"]
    origins = [x.strip() for x in raw.split(",") if x.strip()]
    return origins or ["*"]


app = FastAPI(title="Clothing API", version="0.1")

# сначала auth, потом остальное
app.include_router(auth_router)
app.include_router(catalog_router)

cors_origins = _parse_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------
# Startup
# ----------------------------

@app.on_event("startup")
def _startup():
    # MinIO bucket (может упасть если MinIO не готов — это ок, но лучше логировать)
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning("ensure_bucket failed on startup: %s", e)

    # Seed категорий: только если таблицы уже созданы миграциями и категорий нет
    try:
        with SessionLocal() as db:
            # если таблицы ещё не созданы (после down -v), не падаем в restart-loop
            try:
                db.execute(text("SELECT 1 FROM categories LIMIT 1"))
            except (ProgrammingError, OperationalError) as e:
                logger.warning("DB schema not ready yet (skip seeding categories): %s", e)
                return

            if db.query(Category).count() == 0:
                seed_categories(db)

    except Exception as e:
        logger.warning("startup seeding failed: %s", e)


def seed_categories(db: Session) -> None:
    """
    Минимальное дерево:
      - Одежда (odezhda) -> women/men
      - Обувь (obuv)     -> women/men
      - Аксессуары (aksessuary)
    """
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

    for parent_slug in ("odezhda", "obuv"):
        parent = roots[parent_slug]
        for child_slug, child_name in (("women", "Женщина"), ("men", "Мужчина")):
            c = Category(
                id=str(uuid.uuid4()),
                parent_id=parent.id,
                name=child_name,
                slug=child_slug,
                path=f"{parent_slug}/{child_slug}",
                sort_order=0,
                is_active=True,
                ai_aliases={"aliases": [child_slug]},
            )
            db.add(c)

    db.commit()


@app.get("/health")
def health():
    return {"status": "ok"}


# ----------------------------
# Media Upload (auth + owner_id)
# ----------------------------

class UploadResp(BaseModel):
    media_id: str
    bucket: str
    object_key: str
    url: str


@app.post("/v1/media/upload", response_model=UploadResp)
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    media_id = str(uuid.uuid4())
    ext = guess_ext(file.filename) or "jpg"
    bucket = os.getenv("MINIO_BUCKET", "products")

    object_key = f"{current.id}/original/{media_id}.{ext}"

    put_object(object_key=object_key, data=data, content_type=file.content_type)
    url = f"/media/{bucket}/{object_key}"

    m = Media(
        id=media_id,
        owner_id=current.id,
        bucket=bucket,
        object_key=object_key,
        content_type=file.content_type,
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()

    return UploadResp(media_id=media_id, bucket=bucket, object_key=object_key, url=url)


def guess_ext(filename: Optional[str]) -> Optional[str]:
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in ("jpg", "jpeg", "png", "webp"):
        return "jpg" if ext == "jpeg" else ext
    return None


# ----------------------------
# AI Jobs (auth + owner_id)
# ----------------------------

class CreateJobReq(BaseModel):
    media_id: str
    hint: dict[str, Any] | None = None


class CreateJobResp(BaseModel):
    job_id: str
    status: str


@app.post("/v1/ai/jobs", response_model=CreateJobResp)
def create_ai_job(
    payload: CreateJobReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == payload.media_id).first()
    if not media or media.owner_id != current.id:
        raise HTTPException(status_code=404, detail="media_id not found")

    job_id = str(uuid.uuid4())
    job = AIJob(
        id=job_id,
        owner_id=current.id,
        status="queued",
        media_id=media.id,
        hint=payload.hint or {},
        result_json=None,
        error=None,
        model_version="stub-v1",
        draft_product_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    enqueue_process_job(job_id)
    return CreateJobResp(job_id=job_id, status="queued")


class JobResp(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    draft_product_id: str | None = None


@app.get("/v1/ai/jobs/{job_id}", response_model=JobResp)
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


# ----------------------------
# Categories (global, можно без auth)
# ----------------------------

@app.get("/v1/categories/tree")
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


# ----------------------------
# Products (auth + owner_id)
# ----------------------------

class ProductPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: str | None = None


@app.get("/v1/products/{product_id}")
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    media = db.query(ProductMedia).filter(ProductMedia.product_id == p.id).all()

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
            for m in media
        ],
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@app.patch("/v1/products/{product_id}")
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

    p.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok"}


@app.post("/v1/products/{product_id}/publish")
def publish_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    p.status = "published"
    p.updated_at = datetime.utcnow()
    db.commit()

    enqueue_index_product(product_id)
    return {"status": "ok", "product_id": product_id}