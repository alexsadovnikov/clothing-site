import os
from typing import Any

from fastapi import APIRouter, Query, HTTPException, Depends
from meilisearch import Client as MeiliClient

from auth import get_current_user
from models import User

router = APIRouter(prefix="/v1", tags=["catalog"])


def _meili():
    host = os.getenv("MEILI_HOST")
    key = os.getenv("MEILI_MASTER_KEY")
    index_name = os.getenv("MEILI_INDEX", "products")
    if not host or not key:
        raise HTTPException(status_code=503, detail="MeiliSearch is not configured")
    return MeiliClient(host, key), index_name


def _build_filter(current: User, status: str | None = None, extra: str | None = None) -> str:
    parts = [f'owner_id = "{current.id}"']
    if status:
        parts.append(f'status = "{status}"')
    if extra:
        parts.append(extra)
    return " AND ".join(parts)


@router.get("/search", operation_id="search_catalog")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    resp: dict[str, Any] = idx.search(
        q,
        {
            "limit": limit,
            "offset": offset,
            "filter": _build_filter(current, status=status),
        },
    )

    hits = resp.get("hits", []) or []
    return {
        "items": hits,
        "limit": limit,
        "offset": offset,
        "total": resp.get("estimatedTotalHits"),
        "processing_time_ms": resp.get("processingTimeMs"),
    }


# ✅ Каталог "моих вещей" (не общий магазин)
@router.get("/catalog/products", operation_id="list_catalog_products")
def list_catalog_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    resp: dict[str, Any] = idx.search(
        "",
        {
            "limit": limit,
            "offset": offset,
            "filter": _build_filter(current, status=status),
            "sort": ["updated_at:desc"],
        },
    )

    hits = resp.get("hits", []) or []
    return {
        "items": hits,
        "limit": limit,
        "offset": offset,
        "total": resp.get("estimatedTotalHits"),
        "processing_time_ms": resp.get("processingTimeMs"),
    }


@router.get("/catalog/products/{product_id}", operation_id="get_catalog_product")
def get_catalog_product(
    product_id: str,
    status: str | None = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    resp: dict[str, Any] = idx.search(
        "",
        {
            "limit": 1,
            "offset": 0,
            "filter": _build_filter(current, status=status, extra=f'id = "{product_id}"'),
        },
    )
    hits = resp.get("hits", []) or []
    if not hits:
        raise HTTPException(status_code=404, detail="product not found")
    return hits[0]