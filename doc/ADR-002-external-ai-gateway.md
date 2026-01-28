# ADR-002 — External AI Gateway (EU) for OpenAI Access

**Status:** Accepted  
**Version:** 1.0  
**Date:** 2026-01-27  
**Decision Owner:** Platform / Backend  

---

## Контекст

- Прямой доступ к OpenAI из RU контура нежелателен (секреты + сетевые риски).
- Требуется единая точка контроля, мониторинга и возможной смены провайдера AI.
- Нужен простой “drop-in” интерфейс совместимый с `/v1/chat/completions`.

---

## Решение

Вводится внешний шлюз **ai-gateway** на EU VPS (NL):

- публичный домен: `ai.voicecrm.online`
- протокол: HTTPS (Caddy)
- upstream: Docker контейнер `ai-gateway` на `127.0.0.1:8080`
- аутентификация: заголовок `X-AI-Internal-Token` (shared secret)
- API: `POST /v1/chat/completions` (совместим с OpenAI Chat Completions)

RU сервисы (API/worker) вызывают gateway по HTTPS:
- `AI_PROVIDER=gateway`
- `AI_GATEWAY_URL=https://ai.voicecrm.online`
- `AI_INTERNAL_TOKEN=<shared-secret>`

---

## Последствия

Плюсы:
- ключ OpenAI находится только на EU стороне
- единая точка контроля + возможность добавить rate-limit/logging
- минимальные изменения в RU приложении

Минусы:
- добавляется ещё один сервис и домен
- необходим контроль секретов (token rotation)

---

## Альтернативы

1) Прямой OpenAI из RU (отклонено)
2) VPN/туннели до OpenAI (сложнее в эксплуатации)
3) Полноценный API gateway (Kong/Envoy) — избыточно на данном этапе
