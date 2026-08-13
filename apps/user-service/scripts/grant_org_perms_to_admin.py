#!/usr/bin/env python3
"""
Grant organization management permissions to admin role.

Run this script to grant all organization-related permissions to the admin role.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from src.core.database.engine import get_session_factory
from src.core.database.models import CompositeRoleModel, PermissionModel


ORG_PERMISSION_NAMES = [
    "org:create",
    "org:read",
    "org:list",
    "org:update",
    "org:delete",
    "org:move",
    "org:manage-users",
]


async def grant_org_permissions_to_admin():
    """Grant organization permissions to the admin role."""
    session_maker = get_session_factory()
    
    async with session_maker() as session:
        # Find admin role (try both "admin" and "system-admin")
        result = await session.execute(
            select(CompositeRoleModel).where(
                CompositeRoleModel.name.in_(["admin", "system-admin"])
            )
        )
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            print("✗ Admin role not found. Please ensure the admin or system-admin role exists.")
            sys.exit(1)
        
        print(f"✓ Found admin role (name: {admin_role.name})")
        
        # Get organization permissions
        result = await session.execute(
            select(PermissionModel).where(
                PermissionModel.name.in_(ORG_PERMISSION_NAMES)
            )
        )
        org_permissions = result.scalars().all()
        
        if not org_permissions:
            print("✗ Organization permissions not found. Please run add_org_permissions.py first.")
            sys.exit(1)
        
        print(f"✓ Found {len(org_permissions)} organization permissions")
        
        # Get current permissions (stored as JSONB array)
        current_permissions = set(admin_role.permissions or [])
        
        # Add missing permissions
        added = 0
        for permission in org_permissions:
            if permission.name not in current_permissions:
                current_permissions.add(permission.name)
                added += 1
                print(f"  ✓ Granted: {permission.name}")
            else:
                print(f"  - Already granted: {permission.name}")
        
        if added > 0:
            # Update the permissions array
            admin_role.permissions = list(current_permissions)
            await session.commit()
            print(f"\n✓ Successfully granted {added} permissions to admin role")
        else:
            print("\n✓ Admin role already has all organization permissions")


async def main():
    """Main entry point."""
    print("Granting organization permissions to admin role...\n")
    try:
        await grant_org_permissions_to_admin()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
