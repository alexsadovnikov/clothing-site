# Tests v2.md
## Integration-тесты API (FastAPI + PostgreSQL)

**Дата:** 02-02-2026  
**Статус:** финальная версия  
**Область:** backend / API  
**Обязательно к соблюдению**

---

## 0. Цель

Зафиксировать единые правила написания и запуска integration-тестов, чтобы:
- избежать shared-state и хаоса;
- обеспечить детерминированность тестов;
- упростить добавление новых тестов;
- подготовить проект к CI без рефакторинга.

---

## 1. Что считается integration-тестом

Integration-тест:
- делает реальный HTTP-запрос к FastAPI;
- работает с реальной PostgreSQL;
- использует реальную бизнес-логику;
- управляет состоянием БД.

❌ не unit  
❌ не mocks  
❌ не in-memory DB  

---

## 2. Структура тестов (обязательная)

/app/tests/
│
├── conftest.py
│
├── integration/
│ ├── test_auth_login.py
│ ├── test_auth_register.py
│ ├── test_auth_refresh.py
│ ├── test_health.py
│ └── ...
│
└── unit/


### Запрещено
- `conftest.py` внутри `integration/`
- дублирование фикстур
- собственная инициализация DB в тестах

---

## 3. Базовый conftest.py (эталон)

`/app/tests/conftest.py`

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from apps.api.main import app
from apps.api.db import SessionLocal


@pytest.fixture(scope="session")
def api_client():
    return TestClient(app)


@pytest.fixture(scope="function")
def db():
    session = SessionLocal()
    try:
        session.execute(
            text("TRUNCATE TABLE users RESTART IDENTITY CASCADE")
        )
        session.commit()
        yield session
    finally:
        session.close()

Принцип
каждый тест начинается с чистой БД
никаких rollback
никакого shared-state

4. Правила написания integration-тестов
Базовый шаблон
def test_something(api_client, db):
    resp = api_client.post("/v1/endpoint", json={})
    assert resp.status_code == 200

Обязательно
тест самодостаточный
не зависит от порядка
может запускаться отдельно

5. Работа с тестовыми данными
5.1 Уникальные данные — обязательно
❌ Запрещено:
email = "user@example.com"

✅ Разрешено:
import uuid
def unique_email(prefix="user"):
    return f"{prefix}-{uuid.uuid4()}@example.com"

5.2 Создание данных
Допустимы только два способа:

A. Через API (предпочтительно)
api_client.post("/v1/auth/register", json={...})

B. Через ORM (допустимо)
user = User(...)
db.add(user)
db.commit()

❌ Запрещено:
SessionLocal() в тестах
with SessionLocal() внутри тестов

6. Контракт тестирования
Тест фиксирует текущее поведение API, а не желаемое.
Пример:
def test_refresh_missing_token(api_client):
    resp = api_client.post("/v1/auth/refresh", json={})
    assert resp.status_code == 404


Изменение теста допустимо только при осознанном изменении поведения API.

7. Что тестируем

Разрешено:
HTTP-коды
JSON-контракты
side-effects в БД
case-insensitive поведение
idempotency
soft-delete сценарии

Запрещено:
приватные функции
внутренние методы
предположения о будущем поведении

8. Команды запуска
Все integration-тесты
pytest tests/integration -v

Один файл
pytest tests/integration/test_auth_login.py -v

Один тест
pytest tests/integration/test_auth_login.py::test_login_ok -v


Команды выполняются в контейнере api, где доступен /app.

9. Типовые ошибки
Симптом	Причина	Решение
duplicate key	неуникальные данные	uuid
pytest не видит тест	файл пуст	ls -la
IDE видит, pytest нет	правка вне контейнера	править /app/...
flaky тест	shared state	TRUNCATE
10. Жёсткие запреты

❌ rollback вместо TRUNCATE
❌ несколько conftest.py
❌ зависимость тестов от порядка
❌ ручная подготовка БД
❌ «потом поправим тест»

11. Критерии приёма нового integration-теста

Тест принимается, если:
запускается отдельно
проходит в общем прогоне
не требует ручных действий
читается без контекста
стабилен при повторных запусках

12. Итог
Текущая система тестирования:
стабильна
масштабируема
готова к CI
не требует рефакторинга

13. Следующие шаги (опционально)
Tests v3 — CI + coverage
чек-лист code-review тестов
автозапуск integration-тестов в pipeline


---

Если хочешь — следующим шагом:
- сделаем **Tests v3 (CI + coverage)**  
- или вынесем **короткий executive-summary** для команды/менеджмента  
- или зафиксируем **code-review checklist для тестов**
