# main.py — SINGLE SOURCE OF TRUTH

import os
import uuid
import time
import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from pydantic import BaseModel

from db import get_db, SessionLocal
from storage import ensure_bucket
from models import Category, Media, AIJob, User
from queueing import enqueue_process_job

# routers
from auth import router as auth_router, get_current_user
from search_routes import router as catalog_router
from media_routes import router as media_router

logger = logging.getLogger(__name__)

API_VERSION = os.getenv("API_VERSION", "1").strip() or "1"

# ---------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------

app = FastAPI(title="Clothing API", version="0.1.0")

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# ROUTERS (ЕДИНСТВЕННОЕ МЕСТО ПОДКЛЮЧЕНИЯ)
# ---------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(media_router)  # ← ВАЖНО: /v1/media/upload

# ---------------------------------------------------------------------
# ERROR HANDLING
# ---------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "http_error", "detail": exc.detail},
        headers={"API-Version": API_VERSION},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error"},
        headers={"API-Version": API_VERSION},
    )


@app.middleware("http")
async def add_headers_and_timing(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["API-Version"] = API_VERSION
    response.headers["X-Response-Time-ms"] = str(
        int((time.perf_counter() - t0) * 1000)
    )
    return response


# ---------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------

@app.on_event("startup")
def startup():
    try:
        ensure_bucket()
    except Exception as e:
        logger.warning("MinIO not ready: %s", e)

    try:
        with SessionLocal() as db:
            try:
                db.execute(text("SELECT 1 FROM categories LIMIT 1"))
            except (OperationalError, ProgrammingError):
                logger.warning("Categories table not ready — skip seeding")
                return
            seed_categories(db)
    except Exception as e:
        logger.warning("Seed failed (ignored): %s", e)


def seed_categories(db: Session) -> None:
    def get_or_create(path: str, name: str, slug: str, parent_id: str | None):
        c = db.query(Category).filter(Category.path == path).first()
        if c:
            return c
        c = Category(
            id=str(uuid.uuid4()),
            parent_id=parent_id,
            name=name,
            slug=slug,
            path=path,
            is_active=True,
            sort_order=0,
            ai_aliases={},
        )
        db.add(c)
        db.flush()
        return c

    roots = {
        "odezhda": get_or_create("odezhda", "Одежда", "odezhda", None),
        "obuv": get_or_create("obuv", "Обувь", "obuv", None),
        "aksessuary": get_or_create("aksessuary", "Аксессуары", "aksessuary", None),
    }

    subs = [
        ("odezhda", "women", "Женщинам"),
        ("odezhda", "men", "Мужчинам"),
        ("odezhda", "futbolki", "Футболки"),
        ("obuv", "krossovki", "Кроссовки"),
        ("aksessuary", "sumki", "Сумки"),
    ]

    for root, slug, name in subs:
        parent = roots[root]
        get_or_create(f"{parent.path}/{slug}", name, slug, parent.id)

    db.commit()


# ---------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------
# AI JOBS
# ---------------------------------------------------------------------

class CreateJobReq(BaseModel):
    media_id: str
    hint: dict[str, Any] | None = None


@app.post("/v1/ai/jobs")
def create_ai_job(
    payload: CreateJobReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    media = db.query(Media).filter(Media.id == payload.media_id).first()
    if not media or media.owner_id != current.id:
        raise HTTPException(status_code=404, detail="media not found")

    job_id = str(uuid.uuid4())
    now = datetime.utcnow()

    job = AIJob(
        id=job_id,
        owner_id=current.id,
        media_id=media.id,
        status="queued",
        hint=payload.hint or {},
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()

    enqueue_process_job(job_id)
    return {"job_id": job_id, "status": "queued"}