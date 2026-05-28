FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Healthcheck válido para o modo API (FastAPI). O serviço de worker não expõe HTTP;
# o compose sobrescreve o healthcheck/command desse serviço.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: FastAPI (health + /infer). O compose sobrescreve o command para rodar o worker.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
