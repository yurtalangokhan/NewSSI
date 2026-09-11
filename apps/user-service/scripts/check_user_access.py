#!/usr/bin/env python3
"""Show what each user actually resolves to: role column, role assignments,
admin status and effective permissions.

Use this to explain a mismatch between what the admin Users page shows and
what a user can actually reach - e.g. an "enduser" who still sees the admin
panel because a stale `user_roles` assignment grants an admin role.

    uv run python scripts/check_user_access.py
    uv run python scripts/check_user_access.py demo@demo.com
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select

from src.core.database.engine import get_session_factory
from src.core.database.models import UserModel, UserRoleModel
from src.core.permissions.admin_roles import is_admin_role_name
from src.service.permission_resolver_service import PermissionResolverService


async def check_user_access(email_filter: str | None = None) -> None:
    session_maker = get_session_factory()
    # cache_ttl_seconds=0 so repeated runs never read a stale cached answer.
    resolver = PermissionResolverService(cache_ttl_seconds=0)

    async with session_maker() as session:
        query = select(UserModel).order_by(UserModel.email)
        if email_filter:
            query = query.where(UserModel.email == email_filter)
        users = list((await session.execute(query)).scalars().all())

    if not users:
        print(f"No users found{f' for {email_filter}' if email_filter else ''}")
        return

    for user in users:
        async with session_maker() as session:
            assignments = list(
                (
                    await session.execute(
                        select(UserRoleModel).where(UserRoleModel.user_id == user.id)
                    )
                )
                .scalars()
                .all()
            )

        permissions, is_admin = await resolver.resolve_effective_access(user.id)

        print(f"\n{'=' * 70}\n{user.email}\n{'=' * 70}")
        print(f"  users.role (shown in admin UI) : {user.role}")

        if assignments:
            print("  user_roles assignments         :")
            for a in assignments:
                flags = " [primary]" if a.is_primary else ""
                warn = "  <-- ADMIN" if is_admin_role_name(a.role_name) else ""
                print(f"      - {a.role_name}{flags}{warn}")
        else:
            print("  user_roles assignments         : (none - falls back to users.role)")

        print(f"  RESOLVED is_admin              : {is_admin}")
        print(f"  effective permissions          : {len(permissions)}", end="")
        print(" (wildcard '*' - full access)" if permissions == ["*"] else "")

        stale = [
            a.role_name
            for a in assignments
            if is_admin_role_name(a.role_name) and not is_admin_role_name(user.role)
        ]
        if stale:
            print(
                f"  !! MISMATCH: holds admin role(s) {stale} while users.role is "
                f"'{user.role}'.\n"
                f"     Run 'uv run alembic upgrade head' to revoke stale assignments."
            )


if __name__ == "__main__":
    asyncio.run(check_user_access(sys.argv[1] if len(sys.argv) > 1 else None))
