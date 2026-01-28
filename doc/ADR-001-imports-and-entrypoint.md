# ADR-001 — Absolute Imports and Single API Entrypoint

**Status:** Accepted  
**Version:** 1.0  
**Date:** 2026-01-21  
**Decision Owner:** Platform / Backend  

---

## Контекст

В процессе развития backend-платформы Clothing возникли системные проблемы:

- относительные импорты (`from models import`, `from db import`)
- разное поведение кода в:
  - FastAPI (uvicorn)
  - worker-процессах
  - alembic
  - тестах
- зависимость от текущей рабочей директории
- ошибки вида `ModuleNotFoundError` в Docker / CI

Это делало систему:
- хрупкой,
- плохо масштабируемой,
- непригодной для production.

---

## Проблема

Python по умолчанию:
- разрешает относительные импорты **в зависимости от `cwd`**
- ведёт себя по-разному в CLI, uvicorn, worker, alembic

В результате:
- API «работает», worker — падает
- код нельзя безопасно рефакторить
- невозможно добавить AI-пайплайн без побочных эффектов

---

## Решение

### 1. Ввести единый Python namespace

Вся backend-логика размещена под пространством имён:
apps.api.*
Примеры:
```python
from apps.api.models import User
from apps.api.db import get_db
from apps.api.state_service import change_state

2. Единая точка входа API

Определён единственный entrypoint backend-приложения:
apps.api.main

Запуск:
uvicorn apps.api.main:app
Это гарантирует:
	•	одинаковый sys.path
	•	одинаковую модель импорта
	•	предсказуемое поведение

3. PYTHONPATH зафиксирован

В Dockerfile зафиксировано:
ENV PYTHONPATH=/app

Что обеспечивает:
	•	корректную работу absolute imports
	•	единое поведение локально и в контейнере

Альтернативы (отклонены)

❌ Относительные импорты (from .models import User)
	•	ломаются при запуске как скрипт
	•	плохо работают с alembic / worker

❌ Манипуляции sys.path
	•	неявные
	•	небезопасные
	•	плохо поддерживаемые

❌ Разные entrypoint’ы для API и worker
	•	дублирование логики
	•	расхождение окружений

⸻

Последствия (Consequences)

Положительные
	•	единая архитектура API + worker
	•	предсказуемые импорты
	•	безопасный рефакторинг
	•	масштабируемость AI pipeline
	•	production-grade структура

Отрицательные
	•	требуется переписать старые импорты
	•	небольшая кривая обучения для junior-разработчиков

⸻

Связь с DDD

Решение напрямую поддерживает DDD-подход:
	•	чёткие границы модулей
	•	прозрачные зависимости
	•	отсутствие «магии» импорта

⸻

Связанные документы
	•	ARCHITECTURE.md
	•	AI_ROADMAP.md

⸻

Статус решения

Accepted — используется как обязательный стандарт проекта.

Любые новые модули обязаны:
	•	находиться в apps.api.*
	•	использовать абсолютные импорты
	•	не вводить альтернативные entrypoint’ы

---

Если хочешь, дальше логично:
- **ADR-002: Outbox pattern**
- **ADR-003: AI as async side-effect**
- или **CHECKLIST.md для новых фич**

