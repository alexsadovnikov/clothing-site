FROM python:3.12-slim

WORKDIR /app

COPY services/outbox_consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/events /app/events
COPY apps/api/outbox.py /app/outbox.py
COPY services/outbox_consumer /app

ENV PYTHONPATH=/app

CMD ["python", "consumer.py"]