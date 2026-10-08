"""Command orchestration guards; all database and Keycloak I/O is simulated."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.core.database import import_identity, reconcile_identity


@pytest.mark.parametrize("apply,writers_stopped", [(False, False), (False, True), (True, False)])
async def test_import_requires_both_write_guards_before_any_io(
    monkeypatch, tmp_path, apply, writers_stopped
):
    engine_factory = Mock(side_effect=AssertionError("Database access before authorization guards"))
    runtime = Mock(side_effect=AssertionError("Runtime access before authorization guards"))
    monkeypatch.setattr(import_identity, "create_async_engine", engine_factory)
    monkeypatch.setattr(import_identity, "get_system_settings_service", runtime)
    args = SimpleNamespace(
        apply=apply,
        writers_stopped=writers_stopped,
        output=tmp_path / "mapping.json",
        batch_size=500,
    )
    with pytest.raises(ValueError, match="--apply --writers-stopped"):
        await import_identity.run(args)
    engine_factory.assert_not_called()
    runtime.assert_not_called()
    assert not args.output.exists()


async def test_import_loads_runtime_config_before_opening_admin_session(monkeypatch, tmp_path):
    events = []
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(
        import_identity, "env", SimpleNamespace(database_url="configured-db")
    )
    factory = Mock(return_value=engine)
    monkeypatch.setattr(import_identity, "create_async_engine", factory)
    snapshot = {"users": [], "organizations": []}
    monkeypatch.setattr(import_identity, "read_snapshot", AsyncMock(return_value=snapshot))
    keycloak = SimpleNamespace(realm="environment-realm")

    async def load_runtime():
        events.append("runtime")
        keycloak.realm = "persisted-realm"

    monkeypatch.setattr(
        import_identity,
        "get_system_settings_service",
        lambda: SimpleNamespace(keycloak=keycloak, load_runtime_settings=load_runtime),
    )
    admin = SimpleNamespace(
        _keycloak_request=AsyncMock(
            return_value=httpx.Response(
                200,
                json={"attributes": []},
                request=httpx.Request("GET", "https://example.invalid"),
            )
        )
    )

    @asynccontextmanager
    async def session(configured):
        assert configured is keycloak and configured.realm == "persisted-realm"
        events.append("session")
        yield admin

    monkeypatch.setattr(import_identity, "KeycloakAdminSession", session)

    async def profile(client):
        await client.request("GET", "/users/profile")

    monkeypatch.setattr(import_identity, "ensure_identity_user_profile", profile)
    roles = AsyncMock(return_value={"roles_created": 0, "realm_roles": {}})
    monkeypatch.setattr(import_identity, "ensure_legacy_roles", roles)
    mapping = {"users": {}, "organizations": {}}
    importer = AsyncMock(return_value=mapping)
    monkeypatch.setattr(import_identity, "import_missing_identities", importer)
    assignments = AsyncMock(return_value={"memberships_added": 0, "roles_added": 0})
    monkeypatch.setattr(import_identity, "import_existing_assignments", assignments)
    args = SimpleNamespace(
        apply=True, writers_stopped=True, output=tmp_path / "mapping.json", batch_size=250
    )
    await import_identity.run(args)
    assert events == ["runtime", "session"]
    factory.assert_called_once_with("configured-db")
    roles.assert_awaited_once_with(admin, snapshot, apply=True)
    assert importer.await_args.args == (admin, snapshot)
    assert importer.await_args.kwargs["batch_size"] == 250
    assert importer.await_args.kwargs["concurrency"] == 4
    assert json.loads(args.output.read_text()) == mapping
    assert not args.output.with_suffix(".json.tmp").exists()
    engine.dispose.assert_awaited_once()


def reconcile_args(tmp_path, **updates):
    values = {
        "apply": False,
        "writers_stopped": False,
        "output": tmp_path / "manifest.json",
        "mapping": tmp_path / "mapping.json",
        "user_db_env": "TEST_USER_DB",
        "agent_db_env": "TEST_AGENT_DB",
        "rag_db_env": "TEST_RAG_DB",
        "ignore_external_user_id": ["user2", "user1", "user2"],
    }
    values.update(updates)
    return SimpleNamespace(**values)


async def test_reconcile_requires_stopped_writers_before_reading_files_or_databases(
    monkeypatch, tmp_path
):
    factory = Mock(side_effect=AssertionError("Database access before guard"))
    monkeypatch.setattr(reconcile_identity, "create_async_engine", factory)
    with pytest.raises(ValueError, match="--writers-stopped"):
        await reconcile_identity.run(reconcile_args(tmp_path, apply=True))
    factory.assert_not_called()


async def test_reconcile_never_overwrites_existing_manifest(monkeypatch, tmp_path):
    args = reconcile_args(tmp_path)
    args.output.write_text("preserve existing manifest")
    factory = Mock(side_effect=AssertionError("Database access before output guard"))
    monkeypatch.setattr(reconcile_identity, "create_async_engine", factory)
    with pytest.raises(ValueError, match="Output already exists"):
        await reconcile_identity.run(args)
    assert args.output.read_text() == "preserve existing manifest"
    factory.assert_not_called()


async def test_reconcile_dry_run_uses_runtime_realm_and_records_explicit_exceptions(
    monkeypatch, tmp_path
):
    from src.repository import keycloak_admin_session, keycloak_role_client
    from src.service import (
        keycloak_cutover_inventory,
        keycloak_group_cutover,
        keycloak_role_cutover,
        system_settings_service,
    )

    class Connection:
        async def execute(self, statement):
            return SimpleNamespace(mappings=lambda: [])

        async def run_sync(self, callback):
            return callback(self)

    class Engine:
        def __init__(self):
            self.dispose = AsyncMock()

        @asynccontextmanager
        async def connect(self):
            yield Connection()

        begin = connect

    engines = []

    def create_engine(url):
        assert url in {"user-db", "agent-db", "rag-db"}
        engine = Engine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(reconcile_identity, "create_async_engine", create_engine)
    for kind in ("USER", "AGENT", "RAG"):
        monkeypatch.setenv(f"TEST_{kind}_DB", f"{kind.lower()}-db")
    monkeypatch.setattr(
        reconcile_identity.sa, "inspect", lambda _: SimpleNamespace(has_table=lambda _: True)
    )
    external = Mock(return_value=0)
    monkeypatch.setattr(reconcile_identity, "reconcile_external_database", external)
    state = {"realm": "environment-realm"}
    keycloak = SimpleNamespace(get_realm=lambda: state["realm"])

    async def load_runtime():
        state["realm"] = "persisted-realm"

    monkeypatch.setattr(
        system_settings_service,
        "get_system_settings_service",
        lambda: SimpleNamespace(keycloak=keycloak, load_runtime_settings=load_runtime),
    )

    @asynccontextmanager
    async def session(configured):
        assert configured is keycloak and state["realm"] == "persisted-realm"
        yield "scoped-session"

    monkeypatch.setattr(keycloak_admin_session, "KeycloakAdminSession", session)
    inventory = SimpleNamespace(users={}, groups={})
    loader = AsyncMock(return_value=inventory)
    monkeypatch.setattr(keycloak_cutover_inventory.KeycloakCutoverInventory, "load", loader)
    group = AsyncMock(return_value=0)
    role = AsyncMock(return_value=0)
    profile = AsyncMock(side_effect=AssertionError("Profile writes during dry run"))
    monkeypatch.setattr(keycloak_group_cutover, "reconcile_group_metadata", group)
    monkeypatch.setattr(keycloak_role_cutover, "reconcile_role_metadata", role)
    monkeypatch.setattr(keycloak_role_client, "ensure_identity_user_profile", profile)
    args = reconcile_args(tmp_path)
    args.mapping.write_text(json.dumps({"users": {}, "organizations": {}}))
    await reconcile_identity.run(args)
    manifest = json.loads(args.output.read_text())
    assert manifest["realm"] == "persisted-realm"
    assert manifest["ignored_external_user_ids"] == ["user1", "user2"]
    assert manifest["external_references_verified"] is False
    assert manifest["keycloak_assignments_verified"] is False
    assert len(manifest["source_digest"]) == 64
    loader.assert_awaited_once_with("scoped-session")
    assert all(
        call.kwargs["apply"] is False for call in group.await_args_list + role.await_args_list
    )
    assert all(call.kwargs["apply"] is False for call in external.call_args_list)
    profile.assert_not_awaited()
    for engine in engines:
        engine.dispose.assert_awaited_once()


@pytest.mark.parametrize("value,expected", [(None, 4), ("3", 3)])
def test_import_cli_passes_bounded_concurrency(monkeypatch, tmp_path, value, expected):
    import sys

    captured = []

    async def fake_run(args):
        captured.append(args.concurrency)

    monkeypatch.setattr(import_identity, "run", fake_run)
    arguments = [
        "import_identity",
        "--apply",
        "--writers-stopped",
        "--output",
        str(tmp_path / "map.json"),
    ]
    if value is not None:
        arguments.extend(["--concurrency", value])
    monkeypatch.setattr(sys, "argv", arguments)
    import_identity.main()
    assert captured == [expected]
