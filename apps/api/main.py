import os
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from storage import ensure_bucket, put_object
from db import init_db, SessionLocal
from models import Category, Media, AIJob, Product, ProductMedia
from queueing import enqueue_process_job, enqueue_index_product
from search_routes import router as catalog_router

app = FastAPI(title="Clothing API", version="0.1")
app.include_router(catalog_router)

# CORS — пока максимально открыто (позже можно ужесточить под домен)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Startup
# ----------------------------

@app.on_event("startup")
def _startup():
    init_db()
    ensure_bucket()

    # Seed категорий: запускаем только если таблица пустая
    with SessionLocal() as db:
        if db.query(Category).count() == 0:
            seed_categories(db)


def seed_categories(db):
    """
    Минимальное дерево:
      - Одежда (odezhda) -> women/men
      - Обувь (obuv)     -> women/men
      - Аксессуары (aksessuary)
    """
    root_defs = [
        ("odezhda", "Одежда", None),
        ("obuv", "Обувь", None),
        ("aksessuary", "Аксессуары", None),
    ]

    roots: dict[str, Category] = {}

    for slug, name, _ in root_defs:
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

    # Подразделы women/men для одежды и обуви
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
# Media Upload
# ----------------------------

class UploadResp(BaseModel):
    media_id: str
    bucket: str
    object_key: str
    url: str


@app.post("/v1/media/upload", response_model=UploadResp)
async def upload_media(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    media_id = str(uuid.uuid4())
    ext = guess_ext(file.filename) or "jpg"
    object_key = f"original/{media_id}.{ext}"

    bucket = os.getenv("MINIO_BUCKET", "products")

    # Загрузка в MinIO
    put_object(object_key=object_key, data=data, content_type=file.content_type)

    # URL всегда отдаём через Nginx /media/
    url = f"/media/{bucket}/{object_key}"

    # Записываем метаданные в БД
    with SessionLocal() as db:
        m = Media(
            id=media_id,
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
# AI Jobs
# ----------------------------

class CreateJobReq(BaseModel):
    media_id: str
    hint: dict[str, Any] | None = None


class CreateJobResp(BaseModel):
    job_id: str
    status: str


@app.post("/v1/ai/jobs", response_model=CreateJobResp)
def create_ai_job(payload: CreateJobReq):
    job_id = str(uuid.uuid4())

    with SessionLocal() as db:
        media = db.query(Media).filter(Media.id == payload.media_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="media_id not found")

        job = AIJob(
            id=job_id,
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

    # enqueue в Redis очередь (worker обработает)
    enqueue_process_job(job_id)
    return CreateJobResp(job_id=job_id, status="queued")


class JobResp(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    draft_product_id: str | None = None


@app.get("/v1/ai/jobs/{job_id}", response_model=JobResp)
def get_ai_job(job_id: str):
    with SessionLocal() as db:
        job = db.query(AIJob).filter(AIJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        return JobResp(
            job_id=job.id,
            status=job.status,
            result=job.result_json,
            error=job.error,
            draft_product_id=job.draft_product_id,
        )


# ----------------------------
# Categories
# ----------------------------

@app.get("/v1/categories/tree")
def categories_tree():
    with SessionLocal() as db:
        cats = db.query(Category).all()

        nodes = {
            c.id: {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "path": c.path,
                "children": [],
            }
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
# Products
# ----------------------------

class ProductPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    category_id: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None
    status: str | None = None


@app.get("/v1/products/{product_id}")
def get_product(product_id: str):
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
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
            "media": [{"id": m.id, "url": f"/media/{m.bucket}/{m.object_key}", "kind": m.kind} for m in media],
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }


@app.patch("/v1/products/{product_id}")
def patch_product(product_id: str, patch: ProductPatch):
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
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
def publish_product(product_id: str):
    with SessionLocal() as db:
        p = db.query(Product).filter(Product.id == product_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="product not found")

        p.status = "published"
        p.updated_at = datetime.utcnow()
        db.commit()

    # Индексация в Meili — через очередь (worker)
    enqueue_index_product(product_id)
    return {"status": "ok", "product_id": product_id}