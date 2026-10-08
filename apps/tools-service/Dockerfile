FROM python:3.11-slim AS builder

# pyproject.toml's [tool.uv.sources] points at its local-package siblings
# with paths relative to itself (../../packages/X), matching the real
# repo layout (apps/tools-service/pyproject.toml, packages/X two levels
# up). WORKDIR mirrors that same depth here so `uv sync` resolves those
# paths instead of failing to normalise a path above the image root.
WORKDIR /app/apps/tools-service
RUN pip install --no-cache-dir uv

COPY apps/tools-service/uv.lock apps/tools-service/pyproject.toml ./
COPY packages/config-manager/ /app/packages/config-manager/
COPY packages/localization/ /app/packages/localization/
COPY packages/error-contract/ /app/packages/error-contract/
COPY packages/metrics/ /app/packages/metrics/
COPY packages/observability/ /app/packages/observability/
COPY packages/idempotency/ /app/packages/idempotency/
COPY packages/security/ /app/packages/security/

# Install exactly what the lock file pins. The previous image resolved
# bare, unversioned package names against the package index at build time
# instead, which is how fastmcp silently drifted from pyproject.toml's
# minimum-version constraint to a major version away.
RUN uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

# git: git_tools. unixodbc/tdsodbc: the MSSQL/Oracle SQL connectors.
# default-jdk: java_tools (run_java, compile_java_file, run_jar). nodejs:
# code_tools.run_node/run_npm_command. unzip: java_tools.inspect_jar shells
# out to `unzip -p ... MANIFEST.MF`. curl: the HEALTHCHECK below. All from
# Debian's own apt repository -- the previous image instead fetched a
# shell-installer script for a Docker CLI no tool in this service uses,
# and a separate installer script for Node.js, and executed both directly.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl unzip unixodbc tdsodbc default-jdk nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder /app/apps/tools-service/.venv /app/.venv
COPY apps/tools-service/server.py .
COPY apps/tools-service/src/ src/
COPY apps/tools-service/locales/ locales/

RUN mkdir -p /workspace && chown 10001:10001 /workspace && chmod 700 /workspace

ENV PATH="/app/.venv/bin:$PATH" \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8003 \
    WORKSPACE_DIR=/workspace \
    EXECUTOR_UID=10001 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001
EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8003/health || exit 1

CMD ["python", "server.py"]
