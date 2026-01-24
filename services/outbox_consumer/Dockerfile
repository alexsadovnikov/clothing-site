FROM python:3.12-slim

WORKDIR /app

COPY services/outbox_consumer/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# shared code from repo root context
COPY apps/api/events /app/events
COPY apps/api/outbox.py /app/outbox.py

# consumer code
COPY services/outbox_consumer /app

ENV PYTHONPATH=/app
CMD ["python", "consumer.py"]
