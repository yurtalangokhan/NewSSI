FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir --upgrade pip uv

COPY apps/user-service/pyproject.toml apps/user-service/uv.lock apps/user-service/README.md ./
COPY packages/idempotency-py/ packages/idempotency-py/
COPY packages/i18n-py/ packages/i18n-py/

RUN sed -i \
    -e 's|path = "../../packages/idempotency-py"|path = "packages/idempotency-py"|' \
    -e 's|path = "../../packages/i18n-py"|path = "packages/i18n-py"|' \
    pyproject.toml \
    && uv lock \
    && uv sync --frozen --no-dev --no-install-project

COPY apps/user-service/src/ src/
COPY apps/user-service/alembic.ini ./
COPY apps/user-service/locales/ locales/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]
