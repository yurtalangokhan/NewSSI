import uuid

import pytest

from scripts.seed_organization_load_test import (
    LOAD_TEST_EMAIL_DOMAIN,
    LOAD_TEST_MARKER,
    SeedConfig,
    generate_dataset,
    is_load_test_organization,
    is_load_test_user_email,
)


def test_generate_dataset_builds_exact_deterministic_counts() -> None:
    config = SeedConfig(organizations=31, users=97, max_depth=4, seed="repeatable")

    first = generate_dataset(config)
    second = generate_dataset(config)

    assert first == second
    assert len(first.organizations) == 31
    assert len(first.users) == 97
    assert len(first.memberships) == 97
    assert len(first.layouts) == 31


def test_generated_hierarchy_has_valid_paths_and_respects_max_depth() -> None:
    dataset = generate_dataset(SeedConfig(organizations=80, users=0, max_depth=5, seed="hierarchy"))
    organizations_by_id = {row["id"]: row for row in dataset.organizations}

    for organization in dataset.organizations:
        assert organization["level"] <= 4
        assert organization["path"].endswith(f"/{organization['id']}/")
        if organization["parent_id"] is None:
            assert organization["level"] == 0
            assert organization["path"] == f"/{organization['id']}/"
        else:
            parent = organizations_by_id[organization["parent_id"]]
            assert organization["level"] == parent["level"] + 1
            assert organization["path"] == f"{parent['path']}{organization['id']}/"


def test_users_are_directly_and_evenly_assigned_with_managers() -> None:
    dataset = generate_dataset(SeedConfig(organizations=12, users=120, max_depth=3, seed="members"))
    generated_user_ids = {row["id"] for row in dataset.users}
    generated_organization_ids = {row["id"] for row in dataset.organizations}

    assert {row["user_id"] for row in dataset.memberships} == generated_user_ids
    assert all(row["organization_id"] in generated_organization_ids for row in dataset.memberships)
    member_counts = {
        organization_id: sum(
            membership["organization_id"] == organization_id for membership in dataset.memberships
        )
        for organization_id in generated_organization_ids
    }
    assert max(member_counts.values()) - min(member_counts.values()) <= 1
    assert any(row["role_in_org"] == "unit_manager" for row in dataset.memberships)
    assert all(row["is_primary"] for row in dataset.memberships)


def test_generated_records_use_reserved_cleanup_markers() -> None:
    dataset = generate_dataset(SeedConfig(organizations=3, users=3, seed="cleanup"))

    assert all(is_load_test_organization(row) for row in dataset.organizations)
    assert all(is_load_test_user_email(row["email"]) for row in dataset.users)
    assert all(
        row["metadata_json"]["seed_marker"] == LOAD_TEST_MARKER for row in dataset.organizations
    )
    assert all(row["email"].endswith(f"@{LOAD_TEST_EMAIL_DOMAIN}") for row in dataset.users)
    assert not is_load_test_organization(
        {
            "code": "PRODUCTION",
            "metadata_json": {"seed_marker": LOAD_TEST_MARKER},
        }
    )
    assert not is_load_test_user_email("loadtest-000001@example.com")


def test_existing_root_can_be_used_as_parent() -> None:
    parent_id = uuid.uuid4()
    parent_path = f"/{parent_id}/"

    dataset = generate_dataset(
        SeedConfig(organizations=4, users=0, seed="attached"),
        parent_id=parent_id,
        parent_path=parent_path,
        parent_level=0,
    )

    root = dataset.organizations[0]
    assert root["parent_id"] == parent_id
    assert root["level"] == 1
    assert root["path"] == f"{parent_path}{root['id']}/"


def test_large_level_layout_positions_remain_within_database_bounds() -> None:
    dataset = generate_dataset(
        SeedConfig(organizations=5_000, users=0, max_depth=2, seed="wide-layout")
    )

    assert all(-1_000_000 <= row["position_x"] <= 1_000_000 for row in dataset.layouts)
    assert all(-1_000_000 <= row["position_y"] <= 1_000_000 for row in dataset.layouts)


@pytest.mark.parametrize(
    "config",
    [
        SeedConfig(organizations=0),
        SeedConfig(organizations=1, users=-1),
        SeedConfig(organizations=2, max_depth=0),
        SeedConfig(organizations=2, batch_size=0),
    ],
)
def test_invalid_configuration_is_rejected(config: SeedConfig) -> None:
    with pytest.raises(ValueError):
        generate_dataset(config)
