# apps/api/handlers/registry.py
from typing import Callable, Optional
import importlib

# Реестр обработчиков: event_type → "module.function"
_HANDLERS = {
    "product.created.v1": "handlers.product_created.handle",
    "product.published.v1": "handlers.product_published.handle",
    "product.updated.v1": "handlers.product_updated.handle",
    "product.deleted.v1": "handlers.product_deleted.handle",
    "analytics.view.v1": "handlers.analytics.handle_view",
    "search.index.v1": "handlers.search.handle_index",
    # Добавляйте новые события по мере необходимости
}

def get_handler(event_type: str) -> Optional[Callable]:
    """
    Возвращает обработчик (callable) для указанного типа события.
    Возвращает None, если обработчик не зарегистрирован.
    """
    handler_path = _HANDLERS.get(event_type)
    if not handler_path:
        return None

    try:
        module_path, func_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        print(f"Failed to load handler for {event_type}: {e}")
        return None
