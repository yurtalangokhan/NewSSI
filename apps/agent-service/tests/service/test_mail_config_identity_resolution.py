"""Mail-config owner-identity bridging.

`persona/agent` owner ids are stored as the user-service primary id, while
`mail_config.user_id` is written with the Keycloak ``sub``. These tests pin the
clean bridge: identity resolution happens once at the service edge (delegating
to ``AuthService.resolve_user_identity``), the repository only filters by a
candidate id list, and no code path performs an unscoped (cross-tenant) lookup.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from error_contract import NotFoundError
import pytest
import pytest_asyncio

from infrastructure.db.models.mail_config import MailConfigModel
from infrastructure.db.repositories.mail_config_repo import (
    MailConfigRepository,
    _normalize_user_ids,
)
from service.auth import auth_service as auth_module
from service.auth.auth_service import resolve_known_user_ids

# ---------------------------------------------------------------------------
# _normalize_user_ids (pure)
# ---------------------------------------------------------------------------


def test_normalize_user_ids_dedupes_preserving_order():
    assert _normalize_user_ids(["a", "b", "a", "", None, "c", "b"]) == ["a", "b", "c"]


def test_normalize_user_ids_stringifies():
    assert _normalize_user_ids([1, "1", 2]) == ["1", "2"]


def test_normalize_user_ids_empty():
    assert _normalize_user_ids(None) == []
    assert _normalize_user_ids([]) == []
    assert _normalize_user_ids(["", None]) == []


# ---------------------------------------------------------------------------
# resolve_known_user_ids
# ---------------------------------------------------------------------------


def _stub_auth(resolve_impl):
    return lambda: SimpleNamespace(resolve_user_identity=resolve_impl)


@pytest.mark.asyncio
async def test_resolve_known_user_ids_returns_identity_candidates(monkeypatch):
    async def fake_resolve(*, token, user_id, user):
        assert token is None
        assert user_id == "kc-sub"
        return {"known_user_ids": ["primary-1", "kc-sub"]}

    monkeypatch.setattr(auth_module, "get_auth_service", _stub_auth(fake_resolve))

    assert await resolve_known_user_ids("kc-sub") == ["primary-1", "kc-sub"]


@pytest.mark.asyncio
async def test_resolve_known_user_ids_always_includes_raw_id(monkeypatch):
    async def fake_resolve(*, token, user_id, user):
        return {"known_user_ids": ["primary-1"]}

    monkeypatch.setattr(auth_module, "get_auth_service", _stub_auth(fake_resolve))

    assert await resolve_known_user_ids("kc-sub") == ["primary-1", "kc-sub"]


@pytest.mark.asyncio
async def test_resolve_known_user_ids_falls_back_when_identity_empty(monkeypatch):
    async def fake_resolve(*, token, user_id, user):
        return {"known_user_ids": []}

    monkeypatch.setattr(auth_module, "get_auth_service", _stub_auth(fake_resolve))

    assert await resolve_known_user_ids("dev-user") == ["dev-user"]


@pytest.mark.asyncio
async def test_resolve_known_user_ids_falls_back_on_identity_error(monkeypatch):
    async def boom(*, token, user_id, user):
        raise RuntimeError("user-service unreachable")

    monkeypatch.setattr(auth_module, "get_auth_service", _stub_auth(boom))
    warnings: list[tuple] = []
    monkeypatch.setattr(
        auth_module.logger, "warning", lambda *args, **kwargs: warnings.append(args)
    )

    result = await resolve_known_user_ids("kc-sub")

    assert result == ["kc-sub"]
    assert warnings, "user-service failure must be logged, not swallowed"
    assert "kc-sub" in " ".join(str(part) for part in warnings[0])


@pytest.mark.asyncio
async def test_resolve_known_user_ids_blank_is_empty(monkeypatch):
    def _boom():
        raise AssertionError("must not resolve identity for a blank user id")

    monkeypatch.setattr(auth_module, "get_auth_service", _boom)

    assert await resolve_known_user_ids("") == []
    assert await resolve_known_user_ids(None) == []


@pytest.mark.asyncio
async def test_resolve_user_identity_accepts_no_request(monkeypatch):
    """The runtime (flow/tool) path has no bearer token — resolution must still work."""

    async def fake_get_user(keycloak_id, token=None):
        return {"id": "primary-9", "keycloak_id": keycloak_id}

    monkeypatch.setattr("integrations.user_service_client.get_user_by_keycloak_id", fake_get_user)

    identity = await auth_module.get_auth_service().resolve_user_identity(
        token=None, user_id="11111111-1111-4111-8111-111111111111"
    )

    assert "primary-9" in identity["known_user_ids"]
    assert "11111111-1111-4111-8111-111111111111" in identity["known_user_ids"]


# ---------------------------------------------------------------------------
# Repository: candidate-list filtering, no unscoped lookup
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeMailSession:
    def __init__(self, store: dict[str, MailConfigModel]):
        self.store = store

    async def connection(self, **execution_options: object):
        """``_read_session`` checks out a connection with AUTOCOMMIT options."""
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def add(self, row: MailConfigModel):
        self.store[str(row.id)] = row

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, row):
        pass

    async def execute(self, statement):
        from uuid import UUID

        from sqlalchemy.sql.dml import Update
        from sqlalchemy.sql.selectable import Select

        if isinstance(statement, Select):
            active_rows = [r for r in self.store.values() if r.is_active]
            params = statement.compile().params
            id_val = None
            owners = None
            for k, v in params.items():
                if isinstance(v, (UUID, str)) and (len(str(v)) == 36 or "id" in k):
                    id_val = str(v)
                elif isinstance(v, (list, tuple, set)):
                    owners = set(v)

            if id_val is not None:
                matched = None
                for r in active_rows:
                    if str(r.id) == id_val and (owners is None or r.user_id in owners):
                        matched = r
                        break
                return _Result(row=matched)
            else:
                matched = [r for r in active_rows if (owners is None or r.user_id in owners)]
                matched.sort(key=lambda r: r.name)
                return _Result(rows=matched)

        elif isinstance(statement, Update):
            compiled = statement.compile()
            params = compiled.params
            values = statement._values
            id_val = None
            owners = None
            for k, v in params.items():
                if isinstance(v, (UUID, str)) and (len(str(v)) == 36 or "id" in k):
                    id_val = str(v)
                elif isinstance(v, (list, tuple, set)):
                    owners = set(v)

            matched = None
            for r in self.store.values():
                if id_val and str(r.id) != id_val:
                    continue
                if owners is not None and r.user_id not in owners:
                    continue
                matched = r
                break

            if not matched:
                return _Result(row=None, rowcount=0)

            for col, val in values.items():
                col_name = col.name if hasattr(col, "name") else str(col)
                actual_val = getattr(val, "value", val)
                setattr(matched, col_name, actual_val)

            return _Result(row=matched, rowcount=1)

        return _Result()


@pytest_asyncio.fixture
async def mail_repo(monkeypatch):
    store: dict[str, MailConfigModel] = {}

    def factory():
        return _FakeMailSession(store)

    import infrastructure.db.repositories.base as base_module

    monkeypatch.setattr(base_module, "get_session_factory", lambda: factory)
    yield MailConfigRepository(), factory


async def _seed(factory, *, user_id="owner", name="Config", is_active=True):
    now = datetime.now(UTC)
    row = MailConfigModel(
        id=uuid4(),
        user_id=user_id,
        name=name,
        host="smtp.example.com",
        port=587,
        username="sender@example.com",
        password_encrypted="enc",
        from_email="sender@example.com",
        from_name="Sender",
        security="starttls",
        is_active=is_active,
        last_tested_at=None,
        time_created=now,
        time_updated=now,
    )
    async with factory() as session:
        session.add(row)
        await session.commit()
    return str(row.id)


@pytest.mark.asyncio
async def test_get_by_id_matches_any_candidate_owner(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="keycloak-sub")

    row = await repo.get_by_id(config_id, ["primary-1", "keycloak-sub"])

    assert row is not None
    assert row["id"] == config_id


@pytest.mark.asyncio
async def test_get_by_id_rejects_non_owner(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="owner-a")

    assert await repo.get_by_id(config_id, ["stranger"]) is None


@pytest.mark.asyncio
async def test_get_by_id_empty_candidates_never_leaks(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="owner-a")

    assert await repo.get_by_id(config_id, []) is None


@pytest.mark.asyncio
async def test_list_by_user_ids_unions_candidates(mail_repo):
    repo, factory = mail_repo
    await _seed(factory, user_id="owner-a", name="A")
    await _seed(factory, user_id="owner-b", name="B")
    await _seed(factory, user_id="owner-c", name="C")

    rows = await repo.list_by_user_ids(["owner-a", "owner-b"])

    assert sorted(r["name"] for r in rows) == ["A", "B"]


@pytest.mark.asyncio
async def test_list_by_user_ids_empty_returns_empty(mail_repo):
    repo, factory = mail_repo
    await _seed(factory, user_id="owner-a")

    assert await repo.list_by_user_ids([]) == []


@pytest.mark.asyncio
async def test_update_scopes_to_candidates(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="kc-sub")

    updated = await repo.update(config_id, user_ids=["primary-1", "kc-sub"], name="Renamed")
    assert updated is not None
    assert updated["name"] == "Renamed"

    assert await repo.update(config_id, user_ids=["stranger"], name="Nope") is None


@pytest.mark.asyncio
async def test_update_empty_candidates_returns_none(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="kc-sub")

    assert await repo.update(config_id, user_ids=[], name="Nope") is None


@pytest.mark.asyncio
async def test_deactivate_scopes_to_candidates(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="kc-sub")

    assert await repo.deactivate(config_id, ["stranger"]) is False
    assert await repo.deactivate(config_id, ["primary-1", "kc-sub"]) is True


@pytest.mark.asyncio
async def test_deactivate_empty_candidates_returns_false(mail_repo):
    repo, factory = mail_repo
    config_id = await _seed(factory, user_id="kc-sub")

    assert await repo.deactivate(config_id, []) is False


# ---------------------------------------------------------------------------
# Service: the admin surface is id-addressed, not owner-scoped
#
# SMTP servers are administered centrally and a user binds their own
# credentials to one (see UserMailCredentialModel), so the service addresses a
# config by id and leaves owner filtering to the callers that still want it
# (the repository keeps its ``user_ids`` parameter, covered above).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_list_reads_the_shared_active_catalog():
    from service.auth.mail_config_service import MailConfigService

    repo = SimpleNamespace(list_active=AsyncMock(return_value=[]))

    await MailConfigService(repo=repo).list_configs("kc-sub")

    repo.list_active.assert_awaited_once_with(search=None, page=None, page_size=None)


@pytest.mark.asyncio
async def test_service_get_decrypted_addresses_the_config_by_id():
    from service.auth.mail_config_service import MailConfigService

    repo = SimpleNamespace(get_by_id=AsyncMock(return_value=None))

    with pytest.raises(NotFoundError):
        await MailConfigService(repo=repo).get_decrypted_config("kc-sub", "cfg-1")

    # Decryption is scoped to the user it is resolved for; listing stays
    # platform-wide but masked.
    repo.get_by_id.assert_awaited_once_with("cfg-1", user_ids=["kc-sub"])


@pytest.mark.asyncio
async def test_service_delete_checks_bindings_then_deactivates():
    from service.auth.mail_config_service import MailConfigService

    repo = SimpleNamespace(
        has_active_bindings=AsyncMock(return_value=False),
        deactivate=AsyncMock(return_value=True),
    )

    assert await MailConfigService(repo=repo).delete_config("kc-sub", "cfg-1") == {
        "success": True
    }

    repo.has_active_bindings.assert_awaited_once_with("cfg-1")
    repo.deactivate.assert_awaited_once_with("cfg-1")


@pytest.mark.asyncio
async def test_repository_delete_succeeds_when_config_is_already_inactive():
    from service.auth.mail_config_service import MailConfigService

    repo = SimpleNamespace(
        has_active_bindings=AsyncMock(return_value=False),
        deactivate=AsyncMock(return_value=False),
    )

    result = await MailConfigService(repo=repo).delete_config("kc-sub", "cfg-1")

    assert result == {"success": True}
    repo.has_active_bindings.assert_awaited_once_with("cfg-1")
    repo.deactivate.assert_awaited_once_with("cfg-1")


# ---------------------------------------------------------------------------
# send_email tool: no ambient authority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_tool_refuses_without_user_id():
    from agents.tooling.mail_tooling import wrap_send_email_tool

    tool = wrap_send_email_tool(SimpleNamespace(), mail_config_id="cfg-1", user_id=None)

    out = await tool.ainvoke({"to": ["x@example.com"], "subject": "s", "body": "b"})

    assert "does not have a valid mail configuration" in out


@pytest.mark.asyncio
async def test_send_email_tool_forwards_user_id(monkeypatch):
    from agents.tooling.mail_tooling import wrap_send_email_tool

    # The wrapper sends through the mail service itself rather than handing
    # the resolved SMTP configuration to the tools-service MCP tool, so the
    # caller's identity has to reach `send_email`, not the config lookup.
    sent = AsyncMock(return_value={"success": True, "message": "Email sent."})
    monkeypatch.setattr(
        "service.auth.mail_config_service.get_mail_config_service",
        lambda: SimpleNamespace(send_email=sent),
    )

    inner = SimpleNamespace(ainvoke=AsyncMock(return_value='{"success": true}'))
    tool = wrap_send_email_tool(inner, mail_config_id="cfg-1", user_id="kc-sub")

    await tool.ainvoke({"to": ["x@example.com"], "subject": "s", "body": "b"})

    assert sent.await_count == 1
    kwargs = sent.await_args.kwargs
    assert kwargs["user_id"] == "kc-sub"
    assert kwargs["config_id"] == "cfg-1"
    assert kwargs["owner_user_id"] is None
    inner.ainvoke.assert_not_awaited()
