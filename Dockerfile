FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    requests==2.32.3 \
    psycopg[binary]==3.2.9

COPY collector.py /app/collector.py
COPY schema.sql /app/schema.sql

CMD ["python", "/app/collector.py"]
