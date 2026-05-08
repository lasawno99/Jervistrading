FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/hf_cache \
    PYTHONPATH=/app:/app/Kronos

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/shiyu-coder/Kronos.git /app/Kronos

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Make /app/data writable & ensure it exists for the profit-lock ledger.
# Mount a Railway Volume at /app/data to persist the ledger across redeploys.
RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
