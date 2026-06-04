FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip uv

COPY pyproject.toml uv.lock* ./

# Install only dependencies (not the project)
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY README.md alembic.ini ./

# Install the project itself
RUN uv pip install -e .

ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]