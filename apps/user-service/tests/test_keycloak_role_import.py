"""Resumable creation of prerequisite Keycloak roles for populated cutover."""

from copy import deepcopy

import pytest

from src.service import keycloak_role_cutover as cutover


class RoleAdmin:
    def __init__(self):
        self.roles = {
            ("realm", "existing"): {
                "id": "existing-id",
                "name": "existing",
                "attributes": {"keep": ["yes"]},
            }
        }
        self.children = {"existing-id": [{"id": "infra", "name": "view-users", "clientRole": True}]}
        self.writes = []

    async def request(self, method, path, **kwargs):
        if method != "GET":
            self.writes.append((method, path, deepcopy(kwargs.get("json"))))
        if path == "/clients":
            return [{"id": "svc", "clientId": "user-service"}]
        if path.endswith("/composites"):
            role_id = path.split("/")[2]
            if method == "POST":
                self.children.setdefault(role_id, []).extend(kwargs["json"])
            return self.children.get(role_id, [])
        client_role = path.startswith("/clients/")
        container = "svc" if client_role else "realm"
        if method == "POST":
            value = deepcopy(kwargs["json"])
            value.update(id=f"id-{value['name']}", clientRole=client_role, containerId=container)
            self.roles[container, value["name"]] = value
            return None
        return deepcopy(self.roles.get((container, path.rsplit("/", 1)[-1])))


def snapshot():
    return {
        "composite_roles": [{"name": "existing"}, {"name": "member"}],
        "roles": [{"name": "access", "service_client": "user-service"}],
        "role_hierarchy": [
            {"parent_role": "member", "child_role": "access"},
            {"parent_role": "existing", "child_role": "access"},
        ],
        "role_permissions": [{"role_name": "access", "permission_name": "user:read"}],
    }


@pytest.mark.asyncio
async def test_import_marks_both_role_kinds_from_explicit_snapshot_metadata():
    admin = RoleAdmin()
    source = snapshot()
    source["composite_roles"][1]["is_builtin"] = True
    source["roles"][0]["is_builtin"] = False

    await cutover.ensure_legacy_roles(admin, source, apply=True)

    assert admin.roles["realm", "member"]["attributes"]["agentic.builtin"] == ["true"]
    assert "agentic.builtin" not in admin.roles["svc", "access"]["attributes"]


@pytest.mark.asyncio
async def test_import_marks_builtin_client_role_and_omits_custom_composite_marker():
    admin = RoleAdmin()
    source = snapshot()
    source["composite_roles"][1]["is_builtin"] = False
    source["roles"][0]["is_builtin"] = True

    await cutover.ensure_legacy_roles(admin, source, apply=True)

    assert admin.roles["svc", "access"]["attributes"]["agentic.builtin"] == ["true"]
    assert "agentic.builtin" not in admin.roles["realm", "member"]["attributes"]


@pytest.mark.asyncio
async def test_reconciliation_marks_existing_client_role_from_explicit_metadata():
    admin = RoleAdmin()
    source = snapshot()
    await cutover.ensure_legacy_roles(admin, source, apply=True)
    source["roles"][0]["is_builtin"] = True

    assert await cutover.reconcile_role_metadata(admin, source, apply=True) == 1
    assert admin.writes[-1][2]["attributes"]["agentic.builtin"] == ["true"]


@pytest.mark.asyncio
async def test_reconciliation_upgrades_false_marker_for_confirmed_builtin():
    admin = RoleAdmin()
    source = snapshot()
    await cutover.ensure_legacy_roles(admin, source, apply=True)
    admin.roles["svc", "access"]["attributes"]["agentic.builtin"] = ["false"]
    source["roles"][0]["is_builtin"] = True

    assert await cutover.reconcile_role_metadata(admin, source, apply=True) == 1
    assert admin.writes[-1][2]["attributes"]["agentic.builtin"] == ["true"]


@pytest.mark.asyncio
async def test_roles_are_created_before_edges_and_retry_preserves_existing_state():
    admin = RoleAdmin()
    result = await cutover.ensure_legacy_roles(admin, snapshot(), apply=True)
    assert result["roles_created"] == 2
    assert result["hierarchy_edges_added"] == 2
    assert result["realm_roles"]["member"]["id"] == "id-member"
    assert admin.roles["realm", "existing"]["attributes"] == {"keep": ["yes"]}
    assert admin.children["existing-id"][0]["id"] == "infra"
    assert all(method == "POST" for method, _, _ in admin.writes)
    admin.writes.clear()
    result = await cutover.ensure_legacy_roles(admin, snapshot(), apply=True)
    assert result["roles_created"] == result["hierarchy_edges_added"] == 0
    assert admin.writes == []


@pytest.mark.asyncio
async def test_dry_run_has_no_writes_and_invalid_edges_fail_before_creation():
    admin = RoleAdmin()
    result = await cutover.ensure_legacy_roles(admin, snapshot())
    assert result["roles_created"] == 2
    assert admin.writes == []
    source = snapshot()
    source["role_hierarchy"].append({"parent_role": "member", "child_role": "unknown"})
    with pytest.raises(ValueError, match="Unknown"):
        await cutover.ensure_legacy_roles(admin, source, apply=True)
    assert admin.writes == []


class CountingAssignments(list):
    def __init__(self, values):
        super().__init__(values)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


@pytest.mark.asyncio
async def test_primary_assignments_are_indexed_once_for_bulk_cutover():
    assignments = CountingAssignments(
        [
            {"user_id": "old1", "role_name": "member", "is_primary": True},
            {"user_id": "old2", "role_name": "member", "is_primary": True},
        ]
    )

    class VerifiedAdmin:
        async def request(self, method, path, **kwargs):
            assert method == "GET"
            if path.endswith("/composite"):
                return [{"name": "member"}]
            return {"attributes": {"agentic.primary_role": ["member"]}}

    source = {"users": [{"id": "old1"}, {"id": "old2"}], "user_roles": assignments}
    assert (
        await cutover.reconcile_role_metadata(
            VerifiedAdmin(), source, apply=False, mappings={"users": {"old1": "kc1", "old2": "kc2"}}
        )
        == 0
    )
    assert assignments.iterations == 1


@pytest.mark.asyncio
async def test_role_metadata_verification_preserves_infrastructure_composites():
    admin = RoleAdmin()
    await cutover.ensure_legacy_roles(admin, snapshot(), apply=True)
    assert await cutover.reconcile_role_metadata(admin, snapshot(), apply=False) == 0


@pytest.mark.asyncio
async def test_required_service_client_is_validated_before_creating_roles():
    admin = RoleAdmin()
    original = admin.request

    async def request(method, path, **kwargs):
        if path == "/clients":
            return []
        return await original(method, path, **kwargs)

    admin.request = request
    with pytest.raises(ValueError, match="service-client"):
        await cutover.ensure_legacy_roles(admin, snapshot(), apply=True)
    assert admin.writes == []
