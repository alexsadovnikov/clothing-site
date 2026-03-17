from enum import Enum
from typing import Dict

from pydantic import BaseModel

from apps.api.contracts.state import State


# =========================
# CTA
# =========================

class CTAType(str, Enum):
    UPLOAD = "upload"
    FILL_FIELDS = "fill_fields"
    PUBLISH = "publish"
    NONE = "none"


# =========================
# UI flags
# =========================

class UIFlags(BaseModel):
    can_edit: bool
    show_spinner: bool
    primary_cta: CTAType
    ai_running: bool = False


# =========================
# State → UI map
# =========================

_STATE_UI_MAP: Dict[State, UIFlags] = {
    State.EMPTY: UIFlags(
        can_edit=True,
        show_spinner=False,
        primary_cta=CTAType.UPLOAD,
    ),
    State.EDITABLE: UIFlags(
        can_edit=True,
        show_spinner=False,
        primary_cta=CTAType.FILL_FIELDS,
    ),
    State.AI_RUNNING: UIFlags(
        can_edit=False,
        show_spinner=True,
        primary_cta=CTAType.NONE,
        ai_running=True,
    ),
    State.READY_TO_PUBLISH: UIFlags(
        can_edit=True,
        show_spinner=False,
        primary_cta=CTAType.PUBLISH,
    ),
    State.PUBLISHED: UIFlags(
        can_edit=False,
        show_spinner=False,
        primary_cta=CTAType.NONE,
    ),
}


# =========================
# Public API
# =========================

def ui_for_state(state: State) -> UIFlags:
    """
    Fail-safe UI mapping:
    если state неизвестен — возвращаем EDITABLE
    """
    return _STATE_UI_MAP.get(
        state,
        UIFlags(
            can_edit=True,
            show_spinner=False,
            primary_cta=CTAType.FILL_FIELDS,
        ),
    )
