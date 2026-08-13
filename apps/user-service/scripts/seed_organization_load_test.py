"""Generate and persist deterministic organization-page load-test data."""

import argparse
import asyncio
import sys
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database.engine import close_db_engine, get_session_factory  # noqa: E402
from src.core.database.models.organization_layout_model import (  # noqa: E402
    OrganizationLayoutModel,
)
from src.core.database.models.organization_model import OrganizationModel  # noqa: E402
from src.core.database.models.user_model import UserModel  # noqa: E402
from src.core.database.models.user_organization_model import (  # noqa: E402
    UserOrganizationModel,
)

LOAD_TEST_MARKER = "organization-page-load-test-v1"
LOAD_TEST_CODE_PREFIX = "LOADTEST_"
LOAD_TEST_EMAIL_DOMAIN = "loadtest.invalid"
UUID_NAMESPACE = uuid.UUID("89d85538-094c-51bb-b7d2-bb50d680ac38")


@dataclass(frozen=True)
class SeedConfig:
    """Configuration for one reproducible load-test dataset."""

    organizations: int = 10_000
    users: int = 100_000
    max_depth: int = 7
    batch_size: int = 5_000
    seed: str = "organization-page-load-test"
    include_layouts: bool = True


@dataclass(frozen=True)
class SeedDataset:
    """Rows ready for SQLAlchemy bulk inserts."""

    organizations: list[dict[str, Any]]
    users: list[dict[str, Any]]
    memberships: list[dict[str, Any]]
    layouts: list[dict[str, Any]]


def _validate_config(config: SeedConfig) -> None:
    if config.organizations < 1:
        raise ValueError("organizations must be at least 1")
    if config.users < 0:
        raise ValueError("users cannot be negative")
    if config.max_depth < 1:
        raise ValueError("max_depth must be at least 1")
    if config.organizations > 1 and config.max_depth == 1:
        raise ValueError("max_depth must exceed 1 when generating multiple organizations")
    if config.batch_size < 1:
        raise ValueError("batch_size must be at least 1")


def _stable_uuid(seed: str, entity: str, index: int) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, f"{seed}:{entity}:{index}")


def _branching_factor(organization_count: int, max_depth: int) -> int:
    if organization_count == 1:
        return 1
    for factor in range(2, organization_count + 1):
        capacity = sum(factor**level for level in range(max_depth))
        if capacity >= organization_count:
            return factor
    return organization_count


def generate_dataset(
    config: SeedConfig,
    *,
    parent_id: uuid.UUID | None = None,
    parent_path: str = "",
    parent_level: int = -1,
) -> SeedDataset:
    """Create deterministic rows without connecting to a database."""
    _validate_config(config)
    factor = _branching_factor(config.organizations, config.max_depth)
    organizations: list[dict[str, Any]] = []
    level_ordinals: dict[int, int] = {}

    for index in range(config.organizations):
        organization_id = _stable_uuid(config.seed, "organization", index)
        if index == 0:
            row_parent_id = parent_id
            level = parent_level + 1
            path = f"{parent_path}{organization_id}/" if parent_path else f"/{organization_id}/"
        else:
            parent_index = (index - 1) // factor
            parent = organizations[parent_index]
            row_parent_id = parent["id"]
            level = parent["level"] + 1
            path = f"{parent['path']}{organization_id}/"

        ordinal = level_ordinals.get(level, 0)
        level_ordinals[level] = ordinal + 1
        organizations.append(
            {
                "id": organization_id,
                "name": "Load Test Organization" if index == 0 else f"Load Test Unit {index:05d}",
                "code": f"{LOAD_TEST_CODE_PREFIX}{index:05d}",
                "description": "Synthetic organization-page load-test data",
                "parent_id": row_parent_id,
                "path": path,
                "level": level,
                "order_index": ordinal,
                "is_active": True,
                "metadata_json": {
                    "seed_marker": LOAD_TEST_MARKER,
                    "seed": config.seed,
                    "generated_index": index,
                },
                "created_by": None,
            }
        )

    users: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []
    for index in range(config.users):
        user_id = _stable_uuid(config.seed, "user", index)
        organization = organizations[index % len(organizations)]
        is_manager = index % 20 == 0
        users.append(
            {
                "id": user_id,
                "keycloak_id": None,
                "email": f"loadtest-{index:07d}@{LOAD_TEST_EMAIL_DOMAIN}",
                "username": f"loadtest-{index:07d}",
                "first_name": "Load",
                "last_name": f"User {index:07d}",
                "hashed_password": None,
                "is_active": True,
                "is_verified": True,
                "is_superuser": False,
                "role": "enduser",
                "groups": [LOAD_TEST_MARKER],
                "invited": False,
                "password_configured": False,
                "is_external_keycloak_user": False,
                "team_name": "Organization Load Test",
            }
        )
        memberships.append(
            {
                "id": _stable_uuid(config.seed, "membership", index),
                "user_id": user_id,
                "organization_id": organization["id"],
                "role_in_org": "unit_manager" if is_manager else "member",
                "is_primary": True,
                "is_active": True,
                "assigned_by": None,
            }
        )

    layouts = []
    if config.include_layouts:
        root_level = organizations[0]["level"]
        for organization in organizations:
            peers = level_ordinals[organization["level"]]
            span = min(float(max(peers - 1, 0) * 280), 1_800_000.0)
            step = span / (peers - 1) if peers > 1 else 0.0
            layouts.append(
                {
                    "organization_id": organization["id"],
                    "position_x": -span / 2 + organization["order_index"] * step,
                    "position_y": float((organization["level"] - root_level) * 190),
                }
            )

    return SeedDataset(organizations, users, memberships, layouts)


def is_load_test_organization(row: dict[str, Any]) -> bool:
    """Return whether both organization cleanup markers are present."""
    metadata = row.get("metadata_json") or {}
    return str(row.get("code", "")).startswith(LOAD_TEST_CODE_PREFIX) and (
        metadata.get("seed_marker") == LOAD_TEST_MARKER
    )


def is_load_test_user_email(email: str) -> bool:
    """Return whether an email belongs to the reserved load-test domain."""
    return email.lower().endswith(f"@{LOAD_TEST_EMAIL_DOMAIN}")


def _batches(rows: Sequence[dict[str, Any]], batch_size: int) -> Iterable[Sequence[dict[str, Any]]]:
    for start in range(0, len(rows), batch_size):
        yield rows[start : start + batch_size]


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(
        delete(OrganizationModel).where(
            OrganizationModel.code.startswith(LOAD_TEST_CODE_PREFIX),
            OrganizationModel.metadata_json["seed_marker"].astext == LOAD_TEST_MARKER,
        )
    )
    await session.execute(
        delete(UserModel).where(UserModel.email.endswith(f"@{LOAD_TEST_EMAIL_DOMAIN}"))
    )


async def cleanup() -> None:
    """Delete only records carrying the reserved load-test markers."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await _cleanup(session)


async def seed(config: SeedConfig) -> SeedDataset:
    """Replace the namespaced dataset in one transaction."""
    _validate_config(config)
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await _cleanup(session)
        root = (
            await session.execute(
                select(OrganizationModel).where(OrganizationModel.parent_id.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        dataset = generate_dataset(
            config,
            parent_id=root.id if root else None,
            parent_path=root.path if root else "",
            parent_level=root.level if root else -1,
        )
        tables_and_rows = (
            (OrganizationModel, dataset.organizations),
            (UserModel, dataset.users),
            (UserOrganizationModel, dataset.memberships),
            (OrganizationLayoutModel, dataset.layouts),
        )
        for model, rows in tables_and_rows:
            for batch in _batches(rows, config.batch_size):
                await session.execute(insert(model), batch)
    return dataset


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("seed", "cleanup"), default="seed")
    parser.add_argument("--organizations", type=int, default=10_000)
    parser.add_argument("--users", type=int, default=100_000)
    parser.add_argument("--max-depth", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=5_000)
    parser.add_argument("--seed", default="organization-page-load-test")
    parser.add_argument("--no-layouts", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> None:
    if args.action == "cleanup":
        await cleanup()
        print("Removed organization-page load-test data.")
        return
    config = SeedConfig(
        organizations=args.organizations,
        users=args.users,
        max_depth=args.max_depth,
        batch_size=args.batch_size,
        seed=args.seed,
        include_layouts=not args.no_layouts,
    )
    dataset = await seed(config)
    print(
        f"Seeded {len(dataset.organizations):,} organizations, "
        f"{len(dataset.users):,} users, and {len(dataset.memberships):,} memberships."
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        asyncio.run(_run(args))
    finally:
        asyncio.run(close_db_engine())


if __name__ == "__main__":
    main()
