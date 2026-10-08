FROM python:3.11-slim

# pyproject.toml's [tool.uv.sources] points at its local-package siblings with
# paths relative to itself (../../packages/X), matching the real repo layout.
# WORKDIR mirrors that same depth here so `uv sync` resolves those paths as
# they are. The previous image rewrote them with sed and then ran `uv lock`,
# which regenerated the lock at build time and made the `--frozen` install
# below install whatever resolved then rather than what was reviewed.
WORKDIR /app/apps/rag-service

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq5 libpq-dev && \
    pip install --no-cache-dir --upgrade pip uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY apps/rag-service/pyproject.toml apps/rag-service/uv.lock apps/rag-service/README.md ./
COPY packages/config-manager/ /app/packages/config-manager/
COPY packages/idempotency/ /app/packages/idempotency/
COPY packages/localization/ /app/packages/localization/
COPY packages/security/ /app/packages/security/
COPY packages/error-contract/ /app/packages/error-contract/
COPY packages/metrics/ /app/packages/metrics/
COPY packages/observability/ /app/packages/observability/

RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv /root/.cache/pip

COPY apps/rag-service/src/ src/
COPY apps/rag-service/alembic.ini ./
COPY apps/rag-service/locales/ locales/

RUN uv sync --frozen --no-dev && \
    apt-get purge -y --auto-remove gcc libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /root/.cache/uv /root/.cache/pip

ENV PATH="/app/apps/rag-service/.venv/bin:$PATH"
ENV PYTHONPATH=/app/apps/rag-service

# Run as an unprivileged user: a code-execution bug in the service should not
# start out with root inside the container.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R 10001:10001 /app
USER 10001

EXPOSE 8083

CMD ["python", "-m", "src"]
