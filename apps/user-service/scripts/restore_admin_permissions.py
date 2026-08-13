#!/usr/bin/env python3
"""
Restore admin role permissions by removing organization permissions.

This script removes the organization permissions that were added if they caused issues.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from src.core.database.engine import get_session_factory
from src.core.database.models import CompositeRoleModel


ORG_PERMISSION_NAMES = {
    "org:create",
    "org:read",
    "org:list",
    "org:update",
    "org:delete",
    "org:move",
    "org:manage-users",
}


async def restore_admin_permissions():
    """Remove organization permissions from admin role."""
    session_maker = get_session_factory()
    
    async with session_maker() as session:
        # Find admin role
        result = await session.execute(
            select(CompositeRoleModel).where(
                CompositeRoleModel.name.in_(["admin", "system-admin"])
            )
        )
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            print("✗ Admin role not found")
            sys.exit(1)
        
        print(f"✓ Found role: {admin_role.name}")
        print(f"  Current permissions count: {len(admin_role.permissions)}")
        
        # Remove organization permissions
        original_count = len(admin_role.permissions)
        filtered_permissions = [
            p for p in admin_role.permissions 
            if p not in ORG_PERMISSION_NAMES
        ]
        
        removed_count = original_count - len(filtered_permissions)
        
        if removed_count > 0:
            admin_role.permissions = filtered_permissions
            await session.commit()
            print(f"✓ Removed {removed_count} organization permissions")
            print(f"  New permissions count: {len(filtered_permissions)}")
        else:
            print("✓ No organization permissions found to remove")


async def main():
    """Main entry point."""
    print("Restoring admin role permissions...\n")
    try:
        await restore_admin_permissions()
        print("\n✓ Done! Please try accessing the admin panel again.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
