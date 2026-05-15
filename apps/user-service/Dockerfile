FROM python:3.11-slim

WORKDIR /app

RUN pip install --upgrade pip uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY alembic.ini .

ENV PYTHONPATH=/app

EXPOSE 8090

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8090"]