"""Import missing legacy identities into Keycloak, including load-test records.

Run with --apply --writers-stopped and --output /path/to/mappings.json.
This command never drops SQL tables or changes retained application references.
Retry after an interruption with the same source database; imported provenance
is checked in Keycloak before another record is created.
"""

import argparse
import asyncio
import json
from pathlib import Path

from config_manager import env
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database.identity_cutover import IDENTITY_TABLES
from src.repository.keycloak_admin_session import KeycloakAdminSession
from src.repository.keycloak_role_client import KeycloakRoleClient, ensure_identity_user_profile
from src.service.keycloak_assignment_import import import_existing_assignments
from src.service.keycloak_identity_import import import_missing_identities
from src.service.keycloak_role_cutover import ensure_legacy_roles
from src.service.system_settings_service import get_system_settings_service


async def read_snapshot(engine):
    async with engine.connect() as connection:
        return {
            # table names come from the IDENTITY_TABLES constant, never user input.
            table: [dict(row) for row in (await connection.execute(sa.text(f'SELECT * FROM "{table}"'))).mappings()]  # noqa: S608
            for table in IDENTITY_TABLES
        }


async def run(args):
    if not args.apply or not args.writers_stopped:
        raise ValueError("Import requires --apply --writers-stopped and a pre-cutover backup")
    concurrency = getattr(args, "concurrency", 4)
    if not 1 <= concurrency <= 8:
        raise ValueError("concurrency must be between 1 and 8")
    engine = create_async_engine(env.database_url)
    try:
        snapshot = await read_snapshot(engine)
        settings_service = get_system_settings_service()
        await settings_service.load_runtime_settings()
        async with KeycloakAdminSession(settings_service.keycloak) as keycloak:

            class ProfileClient(KeycloakRoleClient):
                async def request(self, method, path, **kwargs):
                    response = await keycloak._keycloak_request(method, path, **kwargs)
                    response.raise_for_status()
                    return response.json() if response.content else None

            await ensure_identity_user_profile(ProfileClient())
            roles = await ensure_legacy_roles(keycloak, snapshot, apply=True)
            print(f"Roles ready: {roles['roles_created']} created", flush=True)

            def progress(kind, done, total):
                print(f"Imported {kind}: {done}/{total}", flush=True)

            mapping = await import_missing_identities(
                keycloak,
                snapshot,
                batch_size=args.batch_size,
                concurrency=concurrency,
                progress=progress,
            )
            changes = await import_existing_assignments(
                keycloak,
                snapshot,
                mapping,
                roles["realm_roles"],
                apply=True,
            )
            print(f"Existing account assignments reconciled: {changes}", flush=True)
            temporary = args.output.with_suffix(args.output.suffix + ".tmp")
            temporary.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
            temporary.replace(args.output)
            print("Identity mappings verified; run reconciliation before Alembic 0049", flush=True)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--concurrency", type=int, choices=range(1, 9), default=4)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
