from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Optional

app = FastAPI(title="AI Service", version="0.1")

@app.get("/health")
def health():
    return {"status": "ok"}

class AnalyzeReq(BaseModel):
    bucket: str
    object_key: str
    hint: dict[str, Any] | None = None

@app.post("/v1/analyze")
def analyze(req: AnalyzeReq):
    # Заглушка: возвращаем “скелет” результата
    # Позже сюда подключим модель/пайплайн и нормализацию категорий
    return {
        "category_path_suggested": "odezhda/women",
        "category_id": None,  # позже будем маппить в реальный id из categories
        "product_type": "unknown",
        "colors": [],
        "material_guess": [],
        "attributes": {},
        "tags": [],
        "confidence": {"category": 0.1, "type": 0.1},
        "title_suggested": "Товар (черновик)",
        "description_draft": None,
    }