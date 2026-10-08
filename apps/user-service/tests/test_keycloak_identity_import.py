"""Bulk imports preserve identity provenance and existing accounts."""

import json

import pytest

from src.service.keycloak_identity_import import (
    LEGACY_ID,
    build_group_forest,
    build_user_payloads,
    match_users,
)


def test_group_tree_preserves_hierarchy_and_detects_cycles():
    rows = [{"id": "a", "name": "Root"}, {"id": "b", "name": "Child", "parent_id": "a"}]
    forest, paths = build_group_forest(rows)
    assert paths == {"a": "/Root", "b": "/Root/Child"}
    assert forest[0]["subGroups"][0]["attributes"][LEGACY_ID] == ["b"]
    rows[0]["parent_id"] = "b"
    with pytest.raises(ValueError, match="cycle"):
        build_group_forest(rows)


def test_resume_requires_provenance_and_preserves_recorded_subject():
    source = [{"id": "old", "username": "fixture", "email": "f@example.invalid"}]
    live = [{"id": "kc", "username": "fixture", "attributes": {LEGACY_ID: ["old"]}}]
    assert match_users(source, live) == {"old": "kc"}
    live[0]["attributes"] = {}
    with pytest.raises(ValueError, match="collision"):
        match_users(source, live)
    source[0]["keycloak_id"] = "kc"
    assert match_users(source, live) == {"old": "kc"}


def test_email_collision_is_not_silently_merged():
    with pytest.raises(ValueError, match="collision"):
        match_users(
            [{"id": "old", "username": "new", "email": "taken@example.invalid"}],
            [{"id": "kc", "username": "other", "email": "taken@example.invalid"}],
        )


def test_payload_preserves_roles_membership_metadata_and_has_no_credentials():
    data = {
        "users": [
            {
                "id": "u",
                "username": "fixture",
                "role": "enduser",
                "password_configured": False,
                "is_active": True,
                "created_at": "2020-01-01T00:00:00+00:00",
            }
        ],
        "user_roles": [{"user_id": "u", "role_name": "Manager", "is_primary": True}],
        "user_organizations": [
            {
                "id": "membership",
                "user_id": "u",
                "organization_id": "g",
                "assigned_by": "admin",
                "is_primary": True,
                "is_active": True,
            }
        ],
    }
    payload = build_user_payloads(data, {"admin": "kc-admin"}, {"g": "kc-group"}, {"g": "/Root"})[0]
    assert payload["realmRoles"] == ["Manager"]
    assert payload["groups"] == ["/Root"]
    assert payload["attributes"]["agentic.primary_role"] == ["Manager"]
    metadata = json.loads(payload["attributes"]["agenticai.memberships"][0])
    assert metadata["kc-group"]["assigned_by"] == "kc-admin"
    assert "credentials" not in payload and "id" not in payload
    assert payload["createdTimestamp"] == 1577836800000
    data["users"][0]["hashed_password"] = "unhandled-hash"
    with pytest.raises(ValueError, match="password"):
        build_user_payloads(data, {}, {"g": "kc-group"}, {"g": "/Root"})


@pytest.mark.asyncio
async def test_import_resumes_after_response_loss_without_duplicate_or_overwrite():
    import httpx

    from src.service.keycloak_identity_import import import_missing_identities

    class Server:
        users = []
        imports = 0

        async def _keycloak_request(self, method, path, **kwargs):
            if path == "/users":
                value = self.users
            elif path.split("?", 1)[0] == "/groups/count":
                value = {"count": 0}
            elif path.split("?", 1)[0] == "/groups":
                value = []
            elif path == "/partialImport":
                self.imports += 1
                assert kwargs["json"]["ifResourceExists"] == "FAIL"
                self.users = [{"id": "kc", **p} for p in kwargs["json"]["users"]]
                raise TimeoutError("Response lost after server committed")
            else:
                raise AssertionError(path)
            return httpx.Response(
                200, json=value, request=httpx.Request(method, "https://kc" + path)
            )

    server = Server()
    data = {
        "users": [{"id": "legacy", "username": "fixture", "role": "enduser"}],
        "organizations": [],
    }
    with pytest.raises(TimeoutError):
        await import_missing_identities(server, data)
    mapping = await import_missing_identities(server, data)
    assert mapping["users"] == {"legacy": "kc"}
    assert server.imports == 1
