#!/usr/bin/env python3
"""Check admin role permissions."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from src.core.database.engine import get_session_factory
from src.core.database.models import CompositeRoleModel


async def check_admin_role():
    """Check admin role permissions."""
    session_maker = get_session_factory()
    
    async with session_maker() as session:
        result = await session.execute(
            select(CompositeRoleModel).where(
                CompositeRoleModel.name.in_(["admin", "system-admin"])
            )
        )
        role = result.scalar_one_or_none()
        
        if not role:
            print("✗ Admin role not found")
            return
        
        print(f"✓ Found role: {role.name}")
        print(f"  Is admin: {role.is_admin}")
        print(f"  Is builtin: {role.is_builtin}")
        print(f"  Permissions count: {len(role.permissions)}")
        print(f"  First 20 permissions:")
        for perm in role.permissions[:20]:
            print(f"    - {perm}")


if __name__ == "__main__":
    asyncio.run(check_admin_role())
