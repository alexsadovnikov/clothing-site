FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Устанавливаем зависимости AI
COPY apps/ai/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем ВЕСЬ проект
COPY . /app

# Запуск AI
CMD ["uvicorn", "apps.ai.main:app", "--host", "0.0.0.0", "--port", "8002"]
