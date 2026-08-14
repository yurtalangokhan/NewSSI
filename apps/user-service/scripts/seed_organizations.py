"""Seed script to create root organization and assign all existing users."""

import asyncio
import sys
import uuid
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.repository import OrganizationRepository, UserOrganizationRepository, UserRepository


async def seed_default_organization():
    """
    Create default root organization and assign all existing users to it.

    Run this once after adding organization tables.
    """
    org_repo = OrganizationRepository()
    user_org_repo = UserOrganizationRepository()
    user_repo = UserRepository()

    print("=" * 70)
    print("SEEDING DEFAULT ROOT ORGANIZATION")
    print("=" * 70)

    # Check if root organization already exists
    root = await org_repo.get_by_code("ROOT")

    if root:
        print(f"✓ Root organization already exists: {root['name']} (ID: {root['id']})")
    else:
        # Create root organization
        root = await org_repo.create(
            name="Ana Organizasyon",
            code="ROOT",
            description="Varsayılan kök organizasyon",
            parent_id=None,
            metadata={"is_default": True, "created_by_seed": True},
        )
        print(f"✓ Root organization created: {root['name']} (ID: {root['id']})")

    # Get all existing users
    users, total = await user_repo.list_paginated(skip=0, limit=10000)
    print(f"\nFound {total} existing users")

    # Assign each user to root organization (if not already assigned)
    assigned_count = 0
    skipped_count = 0

    for user in users:
        user_id = user.id if hasattr(user, "id") else uuid.UUID(user["id"])

        # Check if user is already in root organization
        existing = await user_org_repo.get_by_user_and_org(user_id, root["id"])

        if existing:
            skipped_count += 1
            continue

        # Assign user to root organization
        await user_org_repo.create(
            user_id=user_id,
            organization_id=root["id"],
            role_in_org="member",
            is_primary=True,  # Set as primary since it's their first org
            assigned_by=None,
        )
        assigned_count += 1

        user_email = user.email if hasattr(user, "email") else user.get("email", "Unknown")
        print(f"  ✓ Assigned: {user_email}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total users:        {total}")
    print(f"Newly assigned:     {assigned_count}")
    print(f"Already assigned:   {skipped_count}")
    print(f"Root organization:  {root['name']} (Code: {root['code']})")
    print("=" * 70)

    if assigned_count > 0:
        print("\n✓ All users have been assigned to the root organization")
    else:
        print("\n✓ All users were already assigned")

    print("\nNext steps:")
    print("1. Create sub-organizations using the API or admin UI")
    print("2. Assign users to specific departments/units")
    print("3. Set unit managers for each organization")
    print("4. Configure resource permissions per organization")


if __name__ == "__main__":
    print("\n🌱 Starting organization seed process...\n")
    try:
        asyncio.run(seed_default_organization())
        print("\n✅ Seed completed successfully!")
    except Exception as e:
        print(f"\n❌ Error during seed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
