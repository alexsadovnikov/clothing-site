FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Устанавливаем зависимости API
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем ВЕСЬ проект, чтобы был apps/
COPY . /app

# Запуск API
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
