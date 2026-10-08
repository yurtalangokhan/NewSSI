FROM python:3.11-slim

# pyproject.toml's [tool.uv.sources] points at its local-package siblings with
# paths relative to itself (../../packages/X), matching the real repo layout.
# WORKDIR mirrors that same depth here so `uv sync` resolves those paths as
# they are. The previous image instead rewrote them with sed and then ran
# `uv lock`, which regenerated the lock at build time and made the `--frozen`
# install below install whatever resolved then rather than what was reviewed.
WORKDIR /app/apps/user-service

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir --upgrade pip uv

COPY apps/user-service/pyproject.toml apps/user-service/uv.lock apps/user-service/README.md ./
COPY packages/config-manager/ /app/packages/config-manager/
COPY packages/idempotency/ /app/packages/idempotency/
COPY packages/localization/ /app/packages/localization/
COPY packages/security/ /app/packages/security/
COPY packages/error-contract/ /app/packages/error-contract/
COPY packages/metrics/ /app/packages/metrics/
COPY packages/observability/ /app/packages/observability/

RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv /root/.cache/pip

COPY apps/user-service/src/ src/
COPY apps/user-service/alembic.ini ./
COPY apps/user-service/locales/ locales/

RUN uv sync --frozen --no-dev \
    && rm -rf /root/.cache/uv /root/.cache/pip

ENV PATH="/app/apps/user-service/.venv/bin:$PATH"
ENV PYTHONPATH=/app/apps/user-service

# Run as an unprivileged user: a code-execution bug in the service should not
# start out with root inside the container.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R 10001:10001 /app
USER 10001

EXPOSE 8090

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]
