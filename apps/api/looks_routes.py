import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from auth import get_current_user
from models import User, Look, LookItem, Product, ProductMedia

router = APIRouter(prefix="/v1", tags=["looks"])


class LookCreate(BaseModel):
    title: str | None = None
    occasion: str | None = None
    season: str | None = None


class LookPatch(BaseModel):
    title: str | None = None
    occasion: str | None = None
    season: str | None = None


class AddLookItemReq(BaseModel):
    product_id: str


def _now() -> datetime:
    return datetime.utcnow()


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
        created_at=now if hasattr(Look, "created_at") else None,
        updated_at=now if hasattr(Look, "updated_at") else None,
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
    if hasattr(Look, "updated_at"):
        q = q.order_by(Look.updated_at.desc().nullslast(), Look.created_at.desc().nullslast())
    else:
        q = q.order_by(Look.created_at.desc().nullslast())

    looks = q.limit(limit).offset(offset).all()

    return {
        "items": [
            {
                "id": l.id,
                "title": l.title,
                "occasion": l.occasion,
                "season": l.season,
                "created_at": l.created_at.isoformat() if getattr(l, "created_at", None) else None,
                "updated_at": l.updated_at.isoformat() if getattr(l, "updated_at", None) else None,
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
    lk = db.query(Look).filter(Look.id == look_id).first()
    if not lk or lk.owner_id != current.id:
        raise HTTPException(status_code=404, detail="look not found")

    link_rows = db.query(LookItem).filter(LookItem.look_id == lk.id).all()
    product_ids = [x.product_id for x in link_rows]

    products: list[Product] = []
    media_by_product: dict[str, list[ProductMedia]] = {}

    if product_ids:
        products = (
            db.query(Product)
            .filter(Product.id.in_(product_ids))
            .filter(Product.owner_id == current.id)
            .all()
        )
        medias = db.query(ProductMedia).filter(ProductMedia.product_id.in_(product_ids)).all()
        for m in medias:
            media_by_product.setdefault(m.product_id, []).append(m)

    prod_map = {p.id: p for p in products}

    items = []
    for pid in product_ids:
        p = prod_map.get(pid)
        if not p:
            # если вещь удалена/не принадлежит — просто пропускаем
            continue
        items.append(
            {
                "id": p.id,
                "status": p.status,
                "title": p.title,
                "category_id": p.category_id,
                "tags": p.tags or [],
                "updated_at": p.updated_at.isoformat() if getattr(p, "updated_at", None) else None,
                "media": [
                    {"id": m.id, "kind": m.kind, "url": f"/media/{m.bucket}/{m.object_key}"}
                    for m in (media_by_product.get(p.id) or [])
                ],
            }
        )

    return {
        "id": lk.id,
        "title": lk.title,
        "occasion": lk.occasion,
        "season": lk.season,
        "created_at": lk.created_at.isoformat() if getattr(lk, "created_at", None) else None,
        "updated_at": lk.updated_at.isoformat() if getattr(lk, "updated_at", None) else None,
        "items": items,
    }


@router.patch("/looks/{look_id}", operation_id="patch_look")
def patch_look(
    look_id: str,
    payload: LookPatch,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = db.query(Look).filter(Look.id == look_id).first()
    if not lk or lk.owner_id != current.id:
        raise HTTPException(status_code=404, detail="look not found")

    if payload.title is not None:
        lk.title = payload.title.strip() or None
    if payload.occasion is not None:
        lk.occasion = payload.occasion.strip() or None
    if payload.season is not None:
        lk.season = payload.season.strip() or None

    if hasattr(lk, "updated_at"):
        lk.updated_at = _now()

    db.commit()
    return {"status": "ok"}


@router.delete("/looks/{look_id}", operation_id="delete_look")
def delete_look(
    look_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = db.query(Look).filter(Look.id == look_id).first()
    if not lk or lk.owner_id != current.id:
        raise HTTPException(status_code=404, detail="look not found")

    db.query(LookItem).filter(LookItem.look_id == lk.id).delete(synchronize_session=False)
    db.delete(lk)
    db.commit()
    return {"status": "ok"}


@router.post("/looks/{look_id}/items", operation_id="add_look_item")
def add_look_item(
    look_id: str,
    payload: AddLookItemReq,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = db.query(Look).filter(Look.id == look_id).first()
    if not lk or lk.owner_id != current.id:
        raise HTTPException(status_code=404, detail="look not found")

    p = db.query(Product).filter(Product.id == payload.product_id).first()
    if not p or p.owner_id != current.id:
        raise HTTPException(status_code=404, detail="product not found")

    existing = (
        db.query(LookItem)
        .filter(LookItem.look_id == lk.id, LookItem.product_id == p.id)
        .first()
    )
    if existing:
        return {"status": "ok", "id": existing.id}

    li = LookItem(
        id=str(uuid.uuid4()),
        look_id=lk.id,
        product_id=p.id,
        created_at=_now() if hasattr(LookItem, "created_at") else None,
    )
    db.add(li)

    if hasattr(lk, "updated_at"):
        lk.updated_at = _now()

    db.commit()
    return {"status": "ok", "id": li.id}


@router.delete("/looks/{look_id}/items/{product_id}", operation_id="remove_look_item")
def remove_look_item(
    look_id: str,
    product_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    lk = db.query(Look).filter(Look.id == look_id).first()
    if not lk or lk.owner_id != current.id:
        raise HTTPException(status_code=404, detail="look not found")

    deleted = (
        db.query(LookItem)
        .filter(LookItem.look_id == lk.id, LookItem.product_id == product_id)
        .delete(synchronize_session=False)
    )

    if deleted and hasattr(lk, "updated_at"):
        lk.updated_at = _now()

    db.commit()
    return {"status": "ok"}