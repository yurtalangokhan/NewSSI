FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

RUN pip install --no-cache-dir --upgrade pip uv

COPY pyproject.toml uv.lock README.md ./

# Install only dependencies (not the project)
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY alembic.ini ./

# Install the project itself into the existing uv-managed environment.
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]
