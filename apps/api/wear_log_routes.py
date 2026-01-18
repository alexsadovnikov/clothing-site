import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from auth import get_current_user
from models import User, WearLog, Product

router = APIRouter(prefix="/v1", tags=["wear_log"])


# ============================================================
# SCHEMAS
# ============================================================

class WearLogCreate(BaseModel):
    product_id_uuid: UUID
    worn_at: datetime | None = None
    context: str | None = None
    notes: str | None = None


# ============================================================
# CREATE
# ============================================================

@router.post("/wear-log", operation_id="create_wear_log")
def create_wear_log(
    payload: WearLogCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # 🔥 UUID-only: ищем продукт только по id_uuid
    product = (
        db.query(Product)
        .filter(Product.id_uuid == payload.product_id_uuid)
        .filter(Product.owner_id == current.id)
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="product not found")

    wl = WearLog(
        id=str(uuid.uuid4()),
        owner_id=current.id,
        product_id_uuid=product.id_uuid,
        worn_at=payload.worn_at or datetime.utcnow(),
        context=(payload.context or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        created_at=datetime.utcnow(),
    )

    db.add(wl)
    db.commit()

    return {
        "id": wl.id,
        "product_id_uuid": str(wl.product_id_uuid),
    }


# ============================================================
# LIST
# ============================================================

@router.get("/wear-log", operation_id="list_wear_log")
def list_wear_log(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
    product_id_uuid: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = db.query(WearLog).filter(WearLog.owner_id == current.id)

    if product_id_uuid:
        q = q.filter(WearLog.product_id_uuid == product_id_uuid)

    if date_from:
        q = q.filter(WearLog.worn_at >= date_from)

    if date_to:
        q = q.filter(WearLog.worn_at <= date_to)

    total = q.count()

    rows = (
        q.order_by(WearLog.worn_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return {
        "items": [
            {
                "id": r.id,
                "product_id_uuid": str(r.product_id_uuid),
                "worn_at": r.worn_at.isoformat(),
                "context": r.context,
                "notes": r.notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
        "total": total,
    }