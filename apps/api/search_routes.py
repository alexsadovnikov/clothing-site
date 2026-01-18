import os
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Query, HTTPException, Depends
from meilisearch import Client as MeiliClient, errors as meili_errors

from auth import get_current_user
from models import User

router = APIRouter(prefix="/v1", tags=["catalog"])


# =============================================================================
# MEILI CLIENT
# =============================================================================

def _meili() -> tuple[MeiliClient, str]:
    host = (os.getenv("MEILI_HOST") or "").strip()
    key = (os.getenv("MEILI_MASTER_KEY") or "").strip()
    index_name = (os.getenv("MEILI_INDEX") or "products").strip()

    if not host or not key:
        raise HTTPException(
            status_code=503,
            detail="Search service is not configured",
        )

    if not host.startswith("http"):
        host = f"http://{host}"

    return MeiliClient(host, key), index_name


# =============================================================================
# FILTER BUILDER (UUID-FIRST)
# =============================================================================

def _build_filter(
    *,
    owner_id: UUID,
    status: Optional[str] = None,
    extra: Optional[str] = None,
) -> str:
    """
    Формирует безопасный Meili-фильтр.
    owner_id — обязателен всегда.
    """
    parts: list[str] = [f'owner_id = "{owner_id}"']

    if status:
        parts.append(f'status = "{status}"')

    if extra:
        parts.append(extra)

    return " AND ".join(parts)


# =============================================================================
# FULL-TEXT SEARCH
# =============================================================================

@router.get("/search", operation_id="search_catalog")
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    try:
        resp: dict[str, Any] = idx.search(
            q,
            {
                "limit": limit,
                "offset": offset,
                "filter": _build_filter(
                    owner_id=current.id,
                    status=status,
                ),
            },
        )
    except meili_errors.MeiliSearchError as e:
        raise HTTPException(status_code=503, detail=str(e))

    hits = resp.get("hits") or []

    return {
        "items": hits,
        "limit": limit,
        "offset": offset,
        "total": resp.get("estimatedTotalHits"),
        "processing_time_ms": resp.get("processingTimeMs"),
    }


# =============================================================================
# MY CATALOG (LIST)
# =============================================================================

@router.get("/catalog/products", operation_id="list_catalog_products")
def list_catalog_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    try:
        resp: dict[str, Any] = idx.search(
            "",
            {
                "limit": limit,
                "offset": offset,
                "filter": _build_filter(
                    owner_id=current.id,
                    status=status,
                ),
                "sort": ["updated_at:desc"],
            },
        )
    except meili_errors.MeiliSearchError as e:
        raise HTTPException(status_code=503, detail=str(e))

    hits = resp.get("hits") or []

    return {
        "items": hits,
        "limit": limit,
        "offset": offset,
        "total": resp.get("estimatedTotalHits"),
        "processing_time_ms": resp.get("processingTimeMs"),
    }


# =============================================================================
# MY CATALOG (SINGLE PRODUCT, UUID)
# =============================================================================

@router.get(
    "/catalog/products/{product_id_uuid}",
    operation_id="get_catalog_product",
)
def get_catalog_product(
    product_id_uuid: UUID,
    status: Optional[str] = Query("published"),
    current: User = Depends(get_current_user),
):
    client, index_name = _meili()
    idx = client.index(index_name)

    try:
        resp: dict[str, Any] = idx.search(
            "",
            {
                "limit": 1,
                "offset": 0,
                "filter": _build_filter(
                    owner_id=current.id,
                    status=status,
                    extra=f'id_uuid = "{product_id_uuid}"',
                ),
            },
        )
    except meili_errors.MeiliSearchError as e:
        raise HTTPException(status_code=503, detail=str(e))

    hits = resp.get("hits") or []
    if not hits:
        raise HTTPException(status_code=404, detail="product not found")

    return hits[0]