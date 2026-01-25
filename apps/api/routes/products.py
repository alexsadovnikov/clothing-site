# apps/api/routes/products.py
from __future__ import annotations

import uuid
from typing import Optional, Literal, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.auth import get_current_user
from apps.api.models import Product, ProductState, User, Media, ProductMedia
from apps.api.events.product import product_created_v1
from apps.api.outbox import write_outbox_event

router = APIRouter(prefix="/v1/products", tags=["products"])


# ============================================================
# Pydantic схемы (requests)
# ============================================================

class CreateDraftReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    attributes: Optional[dict] = None
    tags: Optional[list] = None


class PatchProductReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    attributes: Optional[dict] = None
    tags: Optional[list] = None
    status: Optional[str] = None


class AttachMediaReq(BaseModel):
    media_id: str
    kind: Literal["primary", "gallery", "detail"] = "gallery"


# ============================================================
# Pydantic схемы (responses) — чтобы OpenAPI был нормальным
# ============================================================

class MediaOut(BaseModel):
    id: str
    bucket: str
    object_key: str
    content_type: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None


class ProductOut(BaseModel):
    id: str
    owner_id: str
    status: str
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProductListOut(BaseModel):
    items: List[ProductOut]
    limit: int
    offset: int
    total: int


class ProductCreateOut(BaseModel):
    id: str
    status: str


class ProductPublishOut(BaseModel):
    id: str
    status: str


class ProductMediaAttachOut(BaseModel):
    id: str
    product_id: str
    media_id: str
    kind: str
    created_at: Optional[str] = None


class ProductMediaOut(BaseModel):
    id: str
    product_id: str
    media_id: str
    kind: str
    created_at: Optional[str] = None
    media: MediaOut


class ProductMediaListOut(BaseModel):
    items: List[ProductMediaOut]


# ============================================================
# Products
# ============================================================

@router.get("", response_model=ProductListOut)
def list_my_products(
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
    items = (
        q.order_by(Product.created_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return {
        "items": [
            {
                "id": p.id,
                "owner_id": p.owner_id,
                "status": p.status,
                "title": p.title,
                "description": p.description,
                "category_id": p.category_id,
                "attributes": p.attributes,
                "tags": p.tags,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in items
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.post("", response_model=ProductCreateOut)
def create_draft_product(
    body: CreateDraftReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    pid = str(uuid.uuid4())

    p = Product(
        id=pid,
        owner_id=current.id,
        status=ProductState.DRAFT_EMPTY.value,
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        attributes=body.attributes or {},
        tags=body.tags or [],
    )
    db.add(p)

    evt = product_created_v1(
        product_id=pid,
        owner_id=current.id,
        status=p.status,
        title=p.title,
        category_id=p.category_id,
    )
    write_outbox_event(db, evt)

    db.commit()

    return {"id": p.id, "status": p.status}


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.owner_id == current.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not Found")

    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "status": p.status,
        "title": p.title,
        "description": p.description,
        "category_id": p.category_id,
        "attributes": p.attributes,
        "tags": p.tags,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.patch("/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: str,
    body: PatchProductReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.owner_id == current.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not Found")

    data = body.dict(exclude_unset=True)

    allowed = {"title", "description", "category_id", "attributes", "tags", "status"}
    for k in list(data.keys()):
        if k not in allowed:
            data.pop(k, None)

    for k, v in data.items():
        setattr(p, k, v)

    db.add(p)
    db.commit()
    db.refresh(p)

    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "status": p.status,
        "title": p.title,
        "description": p.description,
        "category_id": p.category_id,
        "attributes": p.attributes,
        "tags": p.tags,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.post("/{product_id}/publish", response_model=ProductPublishOut)
def publish_product(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.owner_id == current.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not Found")

    p.status = ProductState.PUBLISHED.value
    db.add(p)
    db.commit()
    db.refresh(p)

    return {"id": p.id, "status": p.status}


# ============================================================
# Product Media
# ============================================================

@router.post("/{product_id}/media", response_model=ProductMediaAttachOut)
def attach_media(
    product_id: str,
    body: AttachMediaReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # 1) product ownership
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.owner_id == current.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not Found")

    # 2) media ownership
    m = (
        db.query(Media)
        .filter(Media.id == body.media_id, Media.owner_id == current.id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Media Not Found")

    kind = (body.kind or "gallery").strip()

    # 3) идемпотентность: если такая связь уже есть — возвращаем её
    existing = (
        db.query(ProductMedia)
        .filter(
            ProductMedia.product_id == product_id,
            ProductMedia.media_id == body.media_id,
            ProductMedia.kind == kind,
        )
        .first()
    )
    if existing:
        return {
            "id": existing.id,
            "product_id": existing.product_id,
            "media_id": existing.media_id,
            "kind": existing.kind,
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
        }

    try:
        # 4) primary: удаляем только ДРУГОЙ primary (если был)
        if kind == "primary":
            db.query(ProductMedia).filter(
                ProductMedia.product_id == product_id,
                ProductMedia.kind == "primary",
                ProductMedia.media_id != body.media_id,
            ).delete(synchronize_session=False)

        link = ProductMedia(
            id=str(uuid.uuid4()),
            product_id=product_id,
            media_id=body.media_id,
            kind=kind,
        )
        db.add(link)
        db.commit()
        db.refresh(link)

    except IntegrityError:
        db.rollback()
        # на гонках/ретраях: вернём существующее
        again = (
            db.query(ProductMedia)
            .filter(
                ProductMedia.product_id == product_id,
                ProductMedia.media_id == body.media_id,
                ProductMedia.kind == kind,
            )
            .first()
        )
        if again:
            return {
                "id": again.id,
                "product_id": again.product_id,
                "media_id": again.media_id,
                "kind": again.kind,
                "created_at": again.created_at.isoformat() if again.created_at else None,
            }

        raise HTTPException(
            status_code=409,
            detail="Media link already exists or primary already set",
        )

    return {
        "id": link.id,
        "product_id": link.product_id,
        "media_id": link.media_id,
        "kind": link.kind,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("/{product_id}/media", response_model=ProductMediaListOut)
def list_product_media(
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.owner_id == current.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Not Found")

    rows = (
        db.query(ProductMedia, Media)
        .join(Media, Media.id == ProductMedia.media_id)
        .filter(ProductMedia.product_id == product_id)
        .order_by(ProductMedia.created_at.desc())
        .all()
    )

    # Нормализованный контракт: media вложенным объектом
    return {
        "items": [
            {
                "id": pm.id,
                "product_id": pm.product_id,
                "media_id": pm.media_id,
                "kind": pm.kind,
                "created_at": pm.created_at.isoformat() if pm.created_at else None,
                "media": {
                    "id": m.id,
                    "bucket": m.bucket,
                    "object_key": m.object_key,
                    "content_type": m.content_type,
                    "filename": m.filename,
                    "size_bytes": m.size_bytes,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                },
            }
            for pm, m in rows
        ]
    }