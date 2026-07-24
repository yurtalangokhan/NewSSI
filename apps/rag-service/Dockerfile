FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq5 libpq-dev && \
    pip install --no-cache-dir --upgrade pip uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY apps/rag-service/pyproject.toml apps/rag-service/uv.lock apps/rag-service/README.md ./
COPY packages/idempotency-py/ packages/idempotency-py/

RUN sed -i 's|path = "../../packages/idempotency-py"|path = "packages/idempotency-py"|' pyproject.toml \
    && uv lock \
    && uv sync --frozen --no-dev --no-install-project

COPY apps/rag-service/langconnect/ langconnect/
COPY apps/rag-service/alembic.ini ./

RUN uv sync --frozen --no-dev && \
    apt-get purge -y --auto-remove gcc libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8083

CMD ["uvicorn", "langconnect.server:APP", "--host", "0.0.0.0", "--port", "8083"]
