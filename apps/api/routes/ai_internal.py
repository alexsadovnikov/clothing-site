# apps/api/routes/ai_internal.py
from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from minio import Minio
from minio.error import S3Error
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.models import AIJob, Media

router = APIRouter(prefix="/v1", tags=["ai-internal"])


# ----------------------------
# Settings helpers
# ----------------------------
def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    return default


def _require_internal_token(x_ai_internal_token: Optional[str]) -> None:
    """
    Internal auth for worker/api -> /v1/analyze
    """
    token = (os.getenv("AI_INTERNAL_TOKEN") or "").strip()
    if not token:
        # лучше сразу взорваться, чем открыть endpoint наружу
        raise HTTPException(status_code=500, detail="AI_INTERNAL_TOKEN is not configured")
    if (x_ai_internal_token or "").strip() != token:
        raise HTTPException(status_code=401, detail="invalid ai internal token")


def _get_minio() -> Minio:
    endpoint = (os.getenv("MINIO_ENDPOINT") or "").strip()
    access = (os.getenv("MINIO_ACCESS_KEY") or "").strip()
    secret = (os.getenv("MINIO_SECRET_KEY") or "").strip()
    secure = (os.getenv("MINIO_SECURE") or "0").strip().lower() in ("1", "true", "yes")

    if not endpoint or not access or not secret:
        raise HTTPException(status_code=500, detail="minio env is not configured")

    return Minio(endpoint, access_key=access, secret_key=secret, secure=secure)


def _guess_data_url(content_type: Optional[str], raw: bytes) -> str:
    ct = (content_type or "").strip().lower()
    if not ct or "/" not in ct:
        ct = "image/jpeg"
    b64 = base64.b64encode(raw).decode("utf-8")
    return f"data:{ct};base64,{b64}"


def _parse_json_maybe(text: str) -> Any:
    """
    Пытаемся распарсить JSON из ответа модели:
    - чистый JSON
    - JSON в ```...``` блоках
    """
    s = (text or "").strip()
    if not s:
        return None

    if "```" in s:
        parts = s.split("```")
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if p.lower().startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                try:
                    return json.loads(p)
                except Exception:
                    pass

    if s.startswith("{") or s.startswith("["):
        try:
            return json.loads(s)
        except Exception:
            return None

    return None


def _extract_openai_content(chat_completion: Dict[str, Any]) -> str:
    try:
        return (chat_completion.get("choices") or [])[0]["message"]["content"] or ""
    except Exception:
        return ""


# ----------------------------
# API схемы
# ----------------------------
class AnalyzeIn(BaseModel):
    # Новый формат (как в jobs.py)
    bucket: Optional[str] = Field(None, description="MinIO bucket")
    object_key: Optional[str] = Field(None, description="MinIO object key")

    # Legacy формат
    media_id: Optional[str] = Field(None, description="Media UUID")
    job_id: Optional[str] = Field(None, description="AI Job UUID")


@router.post("/analyze")
def analyze(
    payload: AnalyzeIn,
    x_ai_internal_token: Optional[str] = Header(default=None, alias="X-AI-Internal-Token"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Внутренний анализ изображения (worker-safe):
    - auth: X-AI-Internal-Token
    - принимает bucket/object_key (предпочтительно) или media_id/job_id
    - читает объект из MinIO
    - вызывает provider (openai или gateway) и возвращает JSON
    """

    _require_internal_token(x_ai_internal_token)

    if not _env_bool("AI_ENABLED", default=True):
        raise HTTPException(status_code=503, detail="ai disabled")

    provider = (os.getenv("AI_PROVIDER") or "openai").strip().lower()
    if provider not in ("openai", "gateway"):
        raise HTTPException(status_code=500, detail=f"unsupported ai provider: {provider}")

    # ----------------------------
    # Resolve bucket/object_key
    # ----------------------------
    bucket = (payload.bucket or "").strip() if payload.bucket else ""
    object_key = (payload.object_key or "").strip() if payload.object_key else ""

    if not bucket or not object_key:
        # fallback to legacy: media_id/job_id -> DB
        media_id = (payload.media_id or "").strip() if payload.media_id else None
        if not media_id and payload.job_id:
            job_id = (payload.job_id or "").strip()
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            if not job:
                raise HTTPException(status_code=404, detail="job not found")
            media_id = str(job.media_id).strip() if getattr(job, "media_id", None) else None

        if not media_id:
            raise HTTPException(status_code=422, detail="bucket/object_key or media_id/job_id is required")

        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            raise HTTPException(status_code=404, detail="media not found")

        bucket = (getattr(media, "bucket", None) or "").strip()
        object_key = (getattr(media, "object_key", None) or "").strip()
        content_type = getattr(media, "content_type", None)

        if not bucket:
            raise HTTPException(status_code=422, detail="media bucket is empty")
        if not object_key:
            raise HTTPException(status_code=422, detail="media object_key is empty")
    else:
        content_type = None  # неизвестно, определим по дефолту в _guess_data_url

    # ----------------------------
    # Read bytes from MinIO
    # ----------------------------
    minio = _get_minio()
    try:
        resp = minio.get_object(bucket, object_key)
        try:
            raw = resp.read()
        finally:
            resp.close()
            resp.release_conn()
    except S3Error as e:
        raise HTTPException(status_code=502, detail=f"minio error: {e.code}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"minio read failed: {e.__class__.__name__}") from e

    if not raw:
        raise HTTPException(status_code=422, detail="media content is empty")

    max_mb = int((os.getenv("AI_MAX_IMAGE_MB") or "15").strip())
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"image too large (> {max_mb} MB)")

    data_url = _guess_data_url(content_type, raw)

    # ----------------------------
    # Prompts
    # ----------------------------
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    max_tokens = int((os.getenv("OPENAI_MAX_TOKENS") or "600").strip())
    temperature = float((os.getenv("OPENAI_TEMPERATURE") or "0.2").strip())
    strict_json = _env_bool("AI_STRICT_JSON", default=True)

    system_prompt = (
        "Ты ассистент по созданию карточек товаров.\n"
        "Верни ТОЛЬКО валидный JSON со структурой:\n"
        "{"
        '"title_suggested": string, '
        '"description_draft": string, '
        '"attributes": object, '
        '"tags": array[string]'
        "}\n"
        "Без пояснений, без markdown."
    )

    user_prompt = (
        "Проанализируй изображение товара. "
        "Сгенерируй короткий продающий заголовок и нейтральное описание. "
        "attributes заполняй только если уверен (например: цвет, материал, категория). "
        "tags — 3-8 коротких тегов."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    # ----------------------------
    # Provider call
    # ----------------------------
    t0 = time.time()

    try:
        if provider == "openai":
            api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
            if not api_key:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY is empty")

            timeout_s = int((os.getenv("OPENAI_TIMEOUT_S") or "45").strip())
            client = OpenAI(api_key=api_key, timeout=timeout_s)

            r = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=messages,
            )
            # openai>=1.x объект → dict
            raw_resp: Dict[str, Any] = r.model_dump()

        else:  # provider == "gateway"
            gw = (os.getenv("AI_GATEWAY_URL") or "").strip().rstrip("/")
            if not gw:
                raise HTTPException(status_code=500, detail="AI_GATEWAY_URL is empty")

            gw_timeout_s = int((os.getenv("AI_GATEWAY_TIMEOUT_S") or "60").strip())

            resp = requests.post(
                f"{gw}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                headers={
                    "Content-Type": "application/json",
                    # тот же токен, что и для /v1/analyze
                    "X-AI-Internal-Token": (os.getenv("AI_INTERNAL_TOKEN") or "").strip(),
                },
                timeout=(10, gw_timeout_s),
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"gateway http {resp.status_code}: {resp.text[:200]}")
            raw_resp = resp.json() or {}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ai request failed: {e.__class__.__name__}") from e

    dt_ms = int((time.time() - t0) * 1000)

    # ----------------------------
    # Parse response content -> JSON
    # ----------------------------
    text = _extract_openai_content(raw_resp).strip()
    parsed = _parse_json_maybe(text) if text else None

    if strict_json and not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="ai returned non-json content")

    if isinstance(parsed, dict):
        ai = parsed
    else:
        ai = {
            "title_suggested": "Товар",
            "description_draft": "Описание будет уточнено.",
            "attributes": {},
            "tags": [],
        }

    # normalize
    title = str(ai.get("title_suggested") or "").strip() or "Товар"
    desc = str(ai.get("description_draft") or "").strip() or "Описание будет уточнено."
    attrs = ai.get("attributes") if isinstance(ai.get("attributes"), dict) else {}
    tags = ai.get("tags") if isinstance(ai.get("tags"), list) else []

    tags_norm: list[str] = []
    for x in tags:
        s = str(x).strip()
        if s:
            tags_norm.append(s)
    tags_norm = tags_norm[:12]

    return {
        "provider": provider,
        "model": model,
        "ms": dt_ms,
        "title_suggested": title,
        "description_draft": desc,
        "attributes": attrs,
        "tags": tags_norm,
    }