FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    requests==2.32.3 \
    psycopg[binary]==3.2.9 && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    DP_ARCH=$(dpkg --print-architecture) && \
    case "$DP_ARCH" in \
      amd64) DBMATE_ARCH="amd64" ;; \
      arm64) DBMATE_ARCH="arm64" ;; \
      *) echo "Unsupported architecture: $DP_ARCH" && exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/amacneil/dbmate/releases/latest/download/dbmate-linux-${DBMATE_ARCH}" -o /usr/local/bin/dbmate && \
    chmod +x /usr/local/bin/dbmate && \
    rm -rf /var/lib/apt/lists/*

COPY collector/ /app/collector/
COPY migrations/ /app/migrations/

CMD ["python", "-m", "collector"]
