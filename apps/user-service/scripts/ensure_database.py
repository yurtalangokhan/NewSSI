from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg import sql


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name) or dotenv_values(".env").get(name) or default
    if value is None or value == "":
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        raise SystemExit(1)
    return str(value)


def main() -> None:
    service_root = Path(__file__).resolve().parents[1]
    os.chdir(service_root)

    host = _env("POSTGRES_HOST", "localhost")
    port = _env("POSTGRES_PORT", "5432")
    user = _env("POSTGRES_USER")
    password = _env("POSTGRES_PASSWORD")
    database = _env("POSTGRES_DB")

    print("Checking Postgres database...")
    try:
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname="postgres",
            autocommit=True,
            connect_timeout=5,
        ) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (database,),
            ).fetchone()

            if exists:
                print(f"Database already exists: {database}")
                return

            print(f"Creating database: {database}")
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)),
            )
    except psycopg.OperationalError as exc:
        print(
            f"Could not connect to Postgres at {host}:{port} as {user}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
