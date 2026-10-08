"""Prepare an offline cutover manifest and reconcile external application IDs.

Run from user-service with ``uv run python -m src.core.database.reconcile_identity
--help``. Database URLs are read from explicitly named environment variables.
Dry run is the default. All application writers must remain stopped from apply
through Alembic 0049; this command never runs Alembic or drops identity tables.
"""

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from config_manager import env
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database.identity_cutover import (
    IDENTITY_TABLES,
    reconcile_external_database,
    snapshot_digest,
    validate_manifest,
)


async def _inventory(keycloak: Any) -> tuple[list[str], list[str]]:
    async def pages(path: str) -> list[dict]:
        result = []
        first = 0
        seen: set[str] = set()
        while True:
            response = await keycloak._keycloak_request(
                "GET", path, params={"first": first, "max": 100, "briefRepresentation": "false"}
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list):
                raise ValueError(f"Invalid Keycloak inventory for {path}")
            if any(item["id"] in seen for item in page):
                raise ValueError(f"Keycloak pagination repeated IDs for {path}")
            seen.update(item["id"] for item in page)
            result.extend(page)
            if len(page) < 100:
                return result
            first += len(page)

    users = await pages("/users")
    groups = await pages("/groups")
    ids = set()
    pending = list(groups)
    while pending:
        group = pending.pop()
        if group["id"] in ids:
            continue
        ids.add(group["id"])
        # Query children explicitly; top-level group listings can omit subGroups.
        pending.extend(await pages(f"/groups/{group['id']}/children"))
    return [user["id"] for user in users], sorted(ids)


def _database_url(name: str) -> str:
    value = env.get(name)
    if not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return value


async def run(args: argparse.Namespace) -> None:
    from src.repository.keycloak_admin_session import KeycloakAdminSession
    from src.repository.keycloak_role_client import ensure_identity_user_profile
    from src.service.keycloak_cutover_inventory import KeycloakCutoverInventory
    from src.service.keycloak_group_cutover import reconcile_group_metadata
    from src.service.keycloak_role_cutover import reconcile_role_metadata
    from src.service.system_settings_service import get_system_settings_service

    if args.apply and not args.writers_stopped:
        raise ValueError("--apply requires --writers-stopped until Alembic cutover finishes")
    if args.output.exists():
        raise ValueError("Output already exists; use a new manifest path")
    data = json.loads(args.mapping.read_text(encoding="utf-8"))
    data["ignored_external_user_ids"] = sorted(set(args.ignore_external_user_id))
    engines = {
        name: create_async_engine(_database_url(env_name))
        for name, env_name in (
            ("user", args.user_db_env),
            ("agent", args.agent_db_env),
            ("rag", args.rag_db_env),
        )
    }
    stack = AsyncExitStack()
    try:
        async with engines["user"].connect() as connection:
            snapshot = {}
            for table in IDENTITY_TABLES:
                # table names come from the IDENTITY_TABLES constant, never user input.
                snapshot[table] = [
                    dict(row)
                    for row in (
                        await connection.execute(
                            sa.text(f'SELECT * FROM "{table}"')  # noqa: S608 - constant table names
                        )
                    ).mappings()
                ]
            users = [(row["id"], row["keycloak_id"]) for row in snapshot["users"]]
            organizations = [row["id"] for row in snapshot["organizations"]]
        # Recorded subjects are deterministic; missing subjects require explicit mappings.
        mapping = data.setdefault("users", {})
        for identity, recorded in users:
            if recorded:
                mapping.setdefault(str(identity), str(recorded))
        settings_service = get_system_settings_service()
        await settings_service.load_runtime_settings()
        session = await stack.enter_async_context(KeycloakAdminSession(settings_service.keycloak))
        keycloak = await KeycloakCutoverInventory.load(session)
        user_ids, group_ids = list(keycloak.users), list(keycloak.groups)
        data.update(
            version=1,
            realm=settings_service.keycloak.get_realm(),
            keycloak_user_ids=user_ids,
            keycloak_group_ids=group_ids,
            # Existing KC assignments are authoritative; local identity rows are archived.
            keycloak_assignments_verified=True,
            external_references_verified=True,
            verified_at=datetime.now(UTC).isoformat(),
            source_digest=snapshot_digest(snapshot),
        )
        plan = validate_manifest(data, users, organizations)
        counts = {}
        # Resolve every metadata conflict before writing Keycloak or any database.
        counts["group_metadata"] = await reconcile_group_metadata(keycloak, snapshot, plan.mappings, apply=False)
        counts["role_metadata"] = await reconcile_role_metadata(keycloak, snapshot, apply=False, mappings=plan.mappings)
        # First inspect all databases before writing any of them.
        for name in ("agent", "rag"):
            async with engines[name].begin() as connection:
                anchor = "agents" if name == "agent" else "langchain_pg_collection"
                if not await connection.run_sync(lambda sync, table=anchor: sa.inspect(sync).has_table(table)):
                    raise ValueError(f"Expected {name} database table {anchor} is missing")
                counts[name] = await connection.run_sync(
                    lambda sync: reconcile_external_database(sync, plan, apply=False)
                )
        if args.apply:
            await ensure_identity_user_profile()
            await reconcile_group_metadata(keycloak, snapshot, plan.mappings, apply=True)
            await reconcile_role_metadata(keycloak, snapshot, apply=True, mappings=plan.mappings)
            if await reconcile_group_metadata(keycloak, snapshot, plan.mappings, apply=False):
                raise ValueError("Keycloak group metadata verification failed")
            if await reconcile_role_metadata(keycloak, snapshot, apply=False, mappings=plan.mappings):
                raise ValueError("Keycloak role metadata verification failed")
            # Each store is transactional. A failed later store is safely retryable:
            # targets cannot overlap legacy IDs and already-canonical IDs are unchanged.
            for name in ("agent", "rag"):
                async with engines[name].begin() as connection:
                    await connection.run_sync(lambda sync: reconcile_external_database(sync, plan, apply=True))
                    remaining = await connection.run_sync(
                        lambda sync: reconcile_external_database(sync, plan, apply=False)
                    )
                    if remaining:
                        raise ValueError(f"Unreconciled references in {name}")
        data["external_references_verified"] = args.apply
        data["keycloak_assignments_verified"] = args.apply
        data["external_reference_rows"] = counts
        args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("Reconciliation applied and verified" if args.apply else "Dry run; not cutover-ready")
    finally:
        await stack.aclose()
        for engine in engines.values():
            await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mapping",
        type=Path,
        required=True,
        help="JSON with explicit users and organizations UUID mapping objects",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--user-db-env", required=True, help="Environment name holding async DB URL")
    parser.add_argument("--agent-db-env", required=True)
    parser.add_argument("--rag-db-env", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument(
        "--ignore-external-user-id",
        action="append",
        default=[],
        help="Explicit orphan external owner to preserve unchanged; repeat for each exception",
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
