from __future__ import annotations

from typing import Optional, List, Literal

from pydantic import BaseModel, Field


class MediaOut(BaseModel):
    id: str
    bucket: str
    object_key: str
    content_type: Optional[str] = None
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: Optional[str] = None  # ISO8601 string

    class Config:
        from_attributes = True


class ProductMediaOut(BaseModel):
    id: str
    product_id: str
    media_id: str
    kind: Literal["primary", "gallery", "detail"]
    created_at: Optional[str] = None  # ISO8601 string
    media: MediaOut

    class Config:
        from_attributes = True


class ProductMediaListOut(BaseModel):
    items: List[ProductMediaOut] = Field(default_factory=list)


class ProductMediaAttachOut(BaseModel):
    id: str
    product_id: str
    media_id: str
    kind: Literal["primary", "gallery", "detail"]
    created_at: Optional[str] = None  # ISO8601 string

    class Config:
        from_attributes = True
