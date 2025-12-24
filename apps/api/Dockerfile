FROM python:3.12-slim

WORKDIR /app

# 1) зависимости
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 2) код сервиса (ВАЖНО: копируем ВСЕ файлы из apps/api)
COPY . /app/

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]