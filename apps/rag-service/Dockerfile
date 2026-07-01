FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

# libpq5 is needed at runtime by PostgreSQL clients. gcc/libpq-dev are only
# needed while building any source distributions that do not have wheels.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq5 libpq-dev && \
    pip install --no-cache-dir --upgrade pip uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency metadata first for better layer caching.
COPY pyproject.toml uv.lock README.md ./

# Install locked runtime dependencies, but not the project source yet.
RUN uv sync --frozen --no-dev --no-install-project

COPY langconnect/ langconnect/
COPY alembic.ini ./

# Install the project itself into the existing uv-managed environment.
RUN uv sync --frozen --no-dev && \
    apt-get purge -y --auto-remove gcc libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8083

CMD ["uvicorn", "langconnect.server:APP", "--host", "0.0.0.0", "--port", "8083"]
