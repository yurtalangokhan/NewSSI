#!/usr/bin/env python3
"""
Add organization management permissions to the database.

Run this script to add organization-related permissions for the new organization management feature.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from src.core.database.engine import get_session_factory
from src.core.database.models import PermissionModel


ORGANIZATION_PERMISSIONS = [
    {
        "name": "org:create",
        "label": "Create Organization",
        "description": "Create new organization",
        "entity": "organization",
        "service": "user-service",
        "action": "create",
        "is_system": True,
    },
    {
        "name": "org:read",
        "label": "Read Organization",
        "description": "View organization details",
        "entity": "organization",
        "service": "user-service",
        "action": "read",
        "is_system": True,
    },
    {
        "name": "org:list",
        "label": "List Organization",
        "description": "List organizations",
        "entity": "organization",
        "service": "user-service",
        "action": "list",
        "is_system": True,
    },
    {
        "name": "org:update",
        "label": "Update Organization",
        "description": "Update organization details",
        "entity": "organization",
        "service": "user-service",
        "action": "update",
        "is_system": True,
    },
    {
        "name": "org:delete",
        "label": "Delete Organization",
        "description": "Delete organizations",
        "entity": "organization",
        "service": "user-service",
        "action": "delete",
        "is_system": True,
    },
    {
        "name": "org:move",
        "label": "Move Organization",
        "description": "Move organizations in hierarchy",
        "entity": "organization",
        "service": "user-service",
        "action": "move",
        "is_system": True,
    },
    {
        "name": "org:manage-users",
        "label": "Manage Organization Users",
        "description": "Manage users in organizations",
        "entity": "organization",
        "service": "user-service",
        "action": "manage-users",
        "is_system": True,
    },
]


async def add_organization_permissions():
    """Add organization permissions to the database."""
    session_maker = get_session_factory()
    
    async with session_maker() as session:
        # Check which permissions already exist
        result = await session.execute(
            select(PermissionModel.name).where(
                PermissionModel.name.in_([p["name"] for p in ORGANIZATION_PERMISSIONS])
            )
        )
        existing_permissions = {row[0] for row in result.all()}
        
        # Add missing permissions
        added = 0
        for perm_data in ORGANIZATION_PERMISSIONS:
            if perm_data["name"] not in existing_permissions:
                permission = PermissionModel(**perm_data)
                session.add(permission)
                added += 1
                print(f"✓ Added permission: {perm_data['name']}")
            else:
                print(f"- Permission already exists: {perm_data['name']}")
        
        if added > 0:
            await session.commit()
            print(f"\n✓ Successfully added {added} organization permissions")
        else:
            print("\n✓ All organization permissions already exist")


async def main():
    """Main entry point."""
    print("Adding organization management permissions...\n")
    try:
        await add_organization_permissions()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
