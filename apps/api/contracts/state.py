from enum import Enum


class State(str, Enum):
    """
    UI State (frontend contract)

    Значения ДОЛЖНЫ совпадать со значениями Product.status в БД
    """

    EMPTY = "draft_empty"          # только создан, пустой
    EDITABLE = "draft_ready"       # можно редактировать
    AI_RUNNING = "ai_running"      # ИИ работает
    READY_TO_PUBLISH = "ready"     # готов к публикации
    PUBLISHED = "published"        # опубликован
