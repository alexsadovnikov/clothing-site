from typing import Dict, Set

from models import ProductState


class InvalidStateTransition(Exception):
    """
    Бросается, если система пытается сделать запрещённый переход.
    Это НЕ 500, это бизнес-ошибка.
    """
    pass


# ============================================================
# PRODUCT STATE MACHINE
# ============================================================

PRODUCT_STATE_TRANSITIONS: Dict[ProductState, Dict[str, ProductState]] = {
    ProductState.DRAFT: {
        "upload_media": ProductState.UPLOADING_MEDIA,
    },

    ProductState.UPLOADING_MEDIA: {
        "media_uploaded": ProductState.MEDIA_READY,
        "media_failed": ProductState.DRAFT,
    },

    ProductState.MEDIA_READY: {
        "start_ai": ProductState.AI_PENDING,
        "reset": ProductState.DRAFT,
    },

    ProductState.AI_PENDING: {
        "ai_started": ProductState.AI_PROCESSING,
        "ai_failed": ProductState.AI_FAILED,
    },

    ProductState.AI_PROCESSING: {
        "ai_completed": ProductState.AI_READY,
        "ai_failed": ProductState.AI_FAILED,
    },

    ProductState.AI_FAILED: {
        "retry_ai": ProductState.AI_PENDING,
        "reset": ProductState.DRAFT,
    },

    ProductState.AI_READY: {
        "confirm_data": ProductState.READY_FOR_PUBLISH,
        "reset": ProductState.DRAFT,
    },

    ProductState.READY_FOR_PUBLISH: {
        "publish": ProductState.PUBLISHED,
        "reset": ProductState.DRAFT,
    },

    ProductState.PUBLISHED: {
        "archive": ProductState.ARCHIVED,
    },

    ProductState.ARCHIVED: {},
}