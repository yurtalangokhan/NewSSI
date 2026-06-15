#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
until python -c "
import psycopg
import sys
try:
    psycopg.connect(f'host={os.environ[\"POSTGRES_HOST\"]} port={os.environ[\"POSTGRES_PORT\"]} user={os.environ[\"POSTGRES_USER\"]} password={os.environ[\"POSTGRES_PASSWORD\"]}')
    print('PostgreSQL is ready!')
except Exception as e:
    print(f'PostgreSQL not ready: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting user-service..."
exec uv run uvicorn src.main:app --host 0.0.0.0 --port 8090
