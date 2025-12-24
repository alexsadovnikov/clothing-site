import os
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query

from db import SessionLocal
from models import Product, ProductMedia

router = APIRouter(prefix="/v1", tags=["catalog"])

def _product_to_dict(db, p: Product) -> dict[str, Any]:
    media_rows = (
        db.query(ProductMedia)
        .filter(ProductMedia.product_id == p.id)
        .order_by(ProductMedia.kind.asc())
        .all()
    )
    media = [
        {"id": m.id, "url": f"/media/{m.bucket}/{m.object_key}", "kind": m.kind}
        for m in media_rows
    ]
    return {
        "id": p.id,
        "status": p.status,
        "title": p.title,
        "description": p.description,
        "category_id": p.category_id,
        "attributes": p.attributes or {},
        "tags": p.tags or [],
        "media": media,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }

@router.get("/products")
def list_products(
    status: str = Query("published"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    with SessionLocal() as db:
        q = db.query(Product)
        if status:
            q = q.filter(Product.status == status)
        rows = q.order_by(Product.updated_at.desc()).offset(offset).limit(limit).all()
        return {"items": [_product_to_dict(db, p) for p in rows], "limit": limit, "offset": offset, "status": status}

@router.get("/search")
def search_products(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    meili_host = os.getenv("MEILI_HOST", "http://meilisearch:7700").rstrip("/")
    meili_key = os.getenv("MEILI_MASTER_KEY", "")
    index = os.getenv("MEILI_INDEX", "products")

    if not meili_key:
        raise HTTPException(status_code=500, detail="MEILI_MASTER_KEY is not set")

    try:
        r = requests.post(
            f"{meili_host}/indexes/{index}/search",
            headers={"Authorization": f"Bearer {meili_key}", "Content-Type": "application/json"},
            json={"q": q, "limit": limit, "offset": offset},
            timeout=10,
        )
        if r.status_code == 404:
            return {"hits": [], "query": q, "limit": limit, "offset": offset, "note": "index_not_found"}
        r.raise_for_status()
        data = r.json()
        return {
            "query": q,
            "limit": limit,
            "offset": offset,
            "hits": data.get("hits", []),
            "estimatedTotalHits": data.get("estimatedTotalHits"),
            "processingTimeMs": data.get("processingTimeMs"),
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"meilisearch error: {e}")