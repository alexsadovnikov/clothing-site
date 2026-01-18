import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from auth import get_current_user
from models import User, Look, LookItem, Product, ProductMedia

router = APIRouter(prefix="/v1", tags=["looks"])


# ============================================================
# SCHEMAS
# ============================================================

class LookCreate(BaseModel):
    title: str | None = None
    occasion: str | None = None
    season: str | None = None


class LookPatch(BaseModel):
    title: str | None = None
    occasion: str | None = None
    season: str | None = None


class AddLookItemReq(BaseModel):
    product_id_uuid: UUID


def _now() -> datetime:
    return datetime.utcnow()


# ============================================================
# LOOKS
# ============================================================

@router.post("/looks", operation_id="create_look")
def create_look(
    payload: LookCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    now = _now()

    lk = Look(
        id=str(uuid.uuid4()),
        owner_id=current.id,
        title=(payload.title or "").strip() or None,
        occasion=(payload.occasion or "").strip() or None,
        season=(payload.season or "").strip() or None,
        created_at=now,
        updated_at=now,
    )

    db.add(lk)
    db.commit()

    return {"id": lk.id}


@router.get("/looks", operation_id="list_looks")
def list_looks(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    q = db.query(Look).filter(Look.owner_id == current.id)

    total = q.count()

    q = q.order_by(
        Look.updated_at.desc().nullslast(),
        Look.created_at.desc().nullslast(),
    )

    looks = q.limit(limit).offset(offset).all()

    return {
        "items": [
            {
                "id": l.id,
                "title": l.title,
                "occasion": l.occasion,
                "season": l.season,
                "created_at": l.created_at.isoformat(),
                "updated_at": l.updated_at.isoformat(),
            }
            for l in looks
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/looks/{look_id}", operation_id="get_look")
def get_look(
    look_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = (
        db.query(Look)
        .filter(Look.id == look_id, Look.owner_id == current.id)
        .first()
    )
    if not lk:
        raise HTTPException(status_code=404, detail="look not found")

    link_rows = (
        db.query(LookItem)
        .filter(LookItem.look_id == lk.id)
        .all()
    )

    product_uuids = [li.product_id_uuid for li in link_rows]

    products: list[Product] = []
    media_by_product: dict[UUID, list[ProductMedia]] = {}

    if product_uuids:
        products = (
            db.query(Product)
            .filter(
                Product.id_uuid.in_(product_uuids),
                Product.owner_id == current.id,
            )
            .all()
        )

        medias = (
            db.query(ProductMedia)
            .filter(ProductMedia.product_id_uuid.in_(product_uuids))
            .all()
        )

        for m in medias:
            media_by_product.setdefault(m.product_id_uuid, []).append(m)

    prod_map = {p.id_uuid: p for p in products}

    items = []
    for pid in product_uuids:
        p = prod_map.get(pid)
        if not p:
            continue

        items.append(
            {
                "product_id_uuid": str(p.id_uuid),
                "status": p.status,
                "title": p.title,
                "category_id": p.category_id,
                "tags": p.tags or [],
                "updated_at": p.updated_at.isoformat(),
                "media": [
                    {
                        "id": m.id,
                        "kind": m.kind,
                        "url": f"/media/{m.bucket}/{m.object_key}",
                    }
                    for m in media_by_product.get(p.id_uuid, [])
                ],
            }
        )

    return {
        "id": lk.id,
        "title": lk.title,
        "occasion": lk.occasion,
        "season": lk.season,
        "created_at": lk.created_at.isoformat(),
        "updated_at": lk.updated_at.isoformat(),
        "items": items,
    }


@router.patch("/looks/{look_id}", operation_id="patch_look")
def patch_look(
    look_id: str,
    payload: LookPatch,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = (
        db.query(Look)
        .filter(Look.id == look_id, Look.owner_id == current.id)
        .first()
    )
    if not lk:
        raise HTTPException(status_code=404, detail="look not found")

    if payload.title is not None:
        lk.title = payload.title.strip() or None
    if payload.occasion is not None:
        lk.occasion = payload.occasion.strip() or None
    if payload.season is not None:
        lk.season = payload.season.strip() or None

    lk.updated_at = _now()

    db.commit()
    return {"status": "ok"}


@router.delete("/looks/{look_id}", operation_id="delete_look")
def delete_look(
    look_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = (
        db.query(Look)
        .filter(Look.id == look_id, Look.owner_id == current.id)
        .first()
    )
    if not lk:
        raise HTTPException(status_code=404, detail="look not found")

    db.query(LookItem).filter(LookItem.look_id == lk.id).delete(
        synchronize_session=False
    )

    db.delete(lk)
    db.commit()
    return {"status": "ok"}


# ============================================================
# LOOK ITEMS
# ============================================================

@router.post("/looks/{look_id}/items", operation_id="add_look_item")
def add_look_item(
    look_id: str,
    payload: AddLookItemReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = (
        db.query(Look)
        .filter(Look.id == look_id, Look.owner_id == current.id)
        .first()
    )
    if not lk:
        raise HTTPException(status_code=404, detail="look not found")

    product = (
        db.query(Product)
        .filter(
            Product.id_uuid == payload.product_id_uuid,
            Product.owner_id == current.id,
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="product not found")

    existing = (
        db.query(LookItem)
        .filter(
            LookItem.look_id == lk.id,
            LookItem.product_id_uuid == product.id_uuid,
        )
        .first()
    )
    if existing:
        return {"status": "ok", "id": existing.id}

    li = LookItem(
        id=str(uuid.uuid4()),
        look_id=lk.id,
        product_id_uuid=product.id_uuid,
        created_at=_now(),
    )

    db.add(li)
    lk.updated_at = _now()

    db.commit()
    return {"status": "ok", "id": li.id}


@router.delete(
    "/looks/{look_id}/items/{product_id_uuid}",
    operation_id="remove_look_item",
)
def remove_look_item(
    look_id: str,
    product_id_uuid: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = (
        db.query(Look)
        .filter(Look.id == look_id, Look.owner_id == current.id)
        .first()
    )
    if not lk:
        raise HTTPException(status_code=404, detail="look not found")

    deleted = (
        db.query(LookItem)
        .filter(
            LookItem.look_id == lk.id,
            LookItem.product_id_uuid == product_id_uuid,
        )
        .delete(synchronize_session=False)
    )

    if deleted:
        lk.updated_at = _now()

    db.commit()
    return {"status": "ok"}