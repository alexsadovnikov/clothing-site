from pydantic import BaseModel
from .cta import CTAType

class UIFlags(BaseModel):
    can_edit: bool
    can_publish: bool
    primary_cta: CTAType
    show_spinner: bool
    show_progress: bool | None = None
