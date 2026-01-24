# apps/api/routes/products.py
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.auth import get_current_user
from apps.api.models import Product, ProductState, User
from apps.api.events.product import product_created_v1
from apps.api.outbox import write_outbox_event

router = APIRouter(prefix="/v1/products", tags=["products"])


class CreateDraftReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    attributes: Optional[dict] = None
    tags: Optional[list] = None


@router.get("")
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


@router.post("")
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

    # Outbox event inside the same DB transaction
    evt = product_created_v1(
        product_id=pid,
        owner_id=current.id,
        status=p.status,
        title=p.title,
        category_id=p.category_id,
    )
    write_outbox_event(db, evt)

    db.commit()

    return {
        "id": p.id,
        "status": p.status,
    }