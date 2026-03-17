from enum import Enum

class CTAType(str, Enum):
    NONE = "NONE"
    UPLOAD = "UPLOAD"
    WAIT = "WAIT"
    EDIT = "EDIT"
    CONTINUE = "CONTINUE"
    PUBLISH = "PUBLISH"
    SAVE_CHANGES = "SAVE_CHANGES"
    RETRY = "RETRY"
