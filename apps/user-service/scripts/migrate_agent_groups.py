"""
Migration script: Legacy agent_groups → New organization-based permissions.

This script:
1. Reads legacy agent_groups from agent-service database
2. Creates corresponding organizations in user-service
3. Assigns users to those organizations
4. Creates resource permissions for agents
5. Validates migration was successful

Run: python -m scripts.migrate_agent_groups
"""

import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.config import get_settings
from src.repository import (
    OrganizationRepository,
    ResourcePermissionRepository,
    UserOrganizationRepository,
)


async def fetch_legacy_agent_groups():
    """
    Fetch agent_groups from agent-service database.
    
    Note: This requires access to agent-service database.
    You may need to adjust connection string.
    """
    # For now, return mock data structure
    # In production, you'd query the actual agent_groups table
    
    # Example query:
    # SELECT id, name, description, user_ids, persona_ids, created_by
    # FROM agent_groups
    # ORDER BY id
    
    print("⚠️  Using mock data. In production, connect to agent-service DB.")
    
    # Mock data for testing
    return [
        {
            "id": 1,
            "name": "HR Access Group",
            "description": "Access to HR agents",
            "user_ids": [],  # List of user UUID strings
            "persona_ids": [101, 102],  # List of agent/persona IDs
            "created_by": None,
        },
        {
            "id": 2,
            "name": "Engineering Team",
            "description": "Access to engineering agents",
            "user_ids": [],
            "persona_ids": [201, 202, 203],
            "created_by": None,
        },
    ]


async def migrate_agent_groups_to_organizations():
    """
    Main migration function.
    
    Converts legacy agent_groups to:
    - Organizations (under root)
    - User-organization assignments
    - Resource permissions
    """
    settings = get_settings()
    
    org_repo = OrganizationRepository()
    user_org_repo = UserOrganizationRepository()
    perm_repo = ResourcePermissionRepository()

    print("=" * 80)
    print("LEGACY AGENT_GROUPS → ORGANIZATION MIGRATION")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}\n")

    # Step 1: Ensure root organization exists
    print("Step 1: Checking root organization...")
    root_org = await org_repo.get_by_code("ROOT")
    if not root_org:
        print("❌ Root organization not found. Run seed_organizations.py first!")
        return
    print(f"✓ Root organization found: {root_org['name']}\n")

    # Step 2: Fetch legacy agent_groups
    print("Step 2: Fetching legacy agent_groups...")
    legacy_groups = await fetch_legacy_agent_groups()
    print(f"✓ Found {len(legacy_groups)} legacy groups\n")

    # Migration statistics
    stats = {
        "organizations_created": 0,
        "organizations_skipped": 0,
        "users_assigned": 0,
        "permissions_created": 0,
        "errors": [],
    }

    # Step 3: Migrate each group
    print("Step 3: Migrating groups...\n")
    
    for group in legacy_groups:
        print(f"Processing: {group['name']} (ID: {group['id']})")
        
        try:
            # Create organization code
            org_code = f"MIGRATED_AG_{group['id']}"
            org_name = f"{group['name']} (Migrated)"
            
            # Check if already migrated
            existing_org = await org_repo.get_by_code(org_code)
            
            if existing_org:
                print(f"  ⚠️  Already migrated, skipping...")
                stats["organizations_skipped"] += 1
                org = existing_org
            else:
                # Create organization
                org = await org_repo.create(
                    name=org_name,
                    code=org_code,
                    description=f"Migrated from legacy agent_group: {group['description']}",
                    parent_id=root_org["id"],
                    metadata={
                        "legacy_group_id": group["id"],
                        "legacy_group_name": group["name"],
                        "migrated_at": datetime.now().isoformat(),
                    },
                )
                stats["organizations_created"] += 1
                print(f"  ✓ Created organization: {org['name']}")

            # Assign users to organization
            user_ids = group.get("user_ids", [])
            print(f"  Assigning {len(user_ids)} users...")
            
            for user_id_str in user_ids:
                try:
                    user_uuid = uuid.UUID(user_id_str)
                    
                    # Check if already assigned
                    existing = await user_org_repo.get_by_user_and_org(
                        user_uuid, org["id"]
                    )
                    
                    if not existing:
                        await user_org_repo.create(
                            user_id=user_uuid,
                            organization_id=org["id"],
                            role_in_org="member",
                            is_primary=False,
                            assigned_by=None,
                        )
                        stats["users_assigned"] += 1
                        print(f"    ✓ Assigned user: {user_id_str[:8]}...")
                        
                except ValueError as e:
                    error_msg = f"Invalid user_id {user_id_str}: {e}"
                    stats["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")

            # Create resource permissions for agents
            persona_ids = group.get("persona_ids", [])
            print(f"  Creating permissions for {len(persona_ids)} agents...")
            
            for persona_id in persona_ids:
                try:
                    # Check if permission already exists
                    existing_perm = await perm_repo.get_by_org_resource(
                        org["id"], "agent", str(persona_id)
                    )
                    
                    if not existing_perm:
                        await perm_repo.create(
                            resource_type="agent",
                            resource_id=str(persona_id),
                            resource_name=f"Agent {persona_id}",
                            organization_id=org["id"],
                            user_id=None,
                            permission_level="execute",  # Legacy had basic access
                            is_inherited=False,
                            granted_by=None,
                        )
                        stats["permissions_created"] += 1
                        print(f"    ✓ Permission granted for agent: {persona_id}")
                        
                except Exception as e:
                    error_msg = f"Failed to create permission for persona {persona_id}: {e}"
                    stats["errors"].append(error_msg)
                    print(f"    ✗ {error_msg}")

            print()  # Blank line between groups

        except Exception as e:
            error_msg = f"Failed to migrate group {group['name']}: {str(e)}"
            stats["errors"].append(error_msg)
            print(f"  ✗ {error_msg}\n")

    # Step 4: Summary
    print("=" * 80)
    print("MIGRATION SUMMARY")
    print("=" * 80)
    print(f"Legacy groups processed:     {len(legacy_groups)}")
    print(f"Organizations created:       {stats['organizations_created']}")
    print(f"Organizations skipped:       {stats['organizations_skipped']}")
    print(f"Users assigned:              {stats['users_assigned']}")
    print(f"Permissions created:         {stats['permissions_created']}")
    print(f"Errors:                      {len(stats['errors'])}")
    print("=" * 80)

    if stats["errors"]:
        print("\n⚠️  ERRORS ENCOUNTERED:")
        for error in stats["errors"][:10]:  # Show first 10
            print(f"  - {error}")
        if len(stats["errors"]) > 10:
            print(f"  ... and {len(stats["errors"]) - 10} more")

    print("\n✓ Migration completed!")
    print("\nNext steps:")
    print("1. Verify migrated data: GET /api/organizations")
    print("2. Test permission checks with agent-service")
    print("3. Update agent-service to use new permission system")
    print("4. Archive agent_groups table: RENAME TABLE agent_groups TO agent_groups_legacy")
    print("5. Remove /api/agent-groups routes from agent-service")


async def validate_migration():
    """
    Validate migration by comparing legacy and new systems.
    """
    print("\n" + "=" * 80)
    print("VALIDATION")
    print("=" * 80)

    legacy_groups = await fetch_legacy_agent_groups()
    org_repo = OrganizationRepository()
    user_org_repo = UserOrganizationRepository()
    perm_repo = ResourcePermissionRepository()

    all_valid = True

    for group in legacy_groups:
        org_code = f"MIGRATED_AG_{group['id']}"
        org = await org_repo.get_by_code(org_code)

        if not org:
            print(f"✗ Organization not found for group: {group['name']}")
            all_valid = False
            continue

        # Validate users
        for user_id_str in group.get("user_ids", []):
            try:
                user_uuid = uuid.UUID(user_id_str)
                user_org = await user_org_repo.get_by_user_and_org(user_uuid, org["id"])
                if not user_org:
                    print(f"✗ User {user_id_str[:8]} not in org {org['code']}")
                    all_valid = False
            except ValueError:
                pass

        # Validate permissions
        for persona_id in group.get("persona_ids", []):
            perm = await perm_repo.get_by_org_resource(org["id"], "agent", str(persona_id))
            if not perm:
                print(f"✗ Permission not found for agent {persona_id} in org {org['code']}")
                all_valid = False

    if all_valid:
        print("✓ All validations passed!")
    else:
        print("✗ Some validations failed. Review errors above.")

    return all_valid


if __name__ == "__main__":
    print("\n🔄 Starting legacy agent_groups migration...\n")
    
    try:
        asyncio.run(migrate_agent_groups_to_organizations())
        
        # Ask user if they want to run validation
        print("\n" + "-" * 80)
        response = input("Run validation? (y/n): ").strip().lower()
        if response == "y":
            asyncio.run(validate_migration())
        
        print("\n✅ Migration script completed!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
