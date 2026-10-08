"""Connection strings must carry the configured secret, correctly encoded."""

from config_manager import env
from sqlalchemy.engine import make_url

from infrastructure.db import engine as engine_module, startup as startup_module

PASSWORD_WITH_RESERVED_CHARS = "p@ss:w/rd?#[]"


def _set_password(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("POSTGRES_AGENT_SERVICE_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("POSTGRES_AGENT_SERVICE_PASSWORD", value)


def test_async_dsn_contains_the_unmasked_password(monkeypatch) -> None:
    _set_password(monkeypatch, "hunter2")

    url = make_url(engine_module._build_url())

    assert url.password == "hunter2"
    assert "*" not in (url.password or "")


def test_dsn_percent_encodes_reserved_characters(monkeypatch) -> None:
    _set_password(monkeypatch, PASSWORD_WITH_RESERVED_CHARS)

    url = make_url(engine_module._build_url())

    assert url.password == PASSWORD_WITH_RESERVED_CHARS


def test_sync_driver_dsn_is_also_unmasked(monkeypatch) -> None:
    _set_password(monkeypatch, "hunter2")

    url = make_url(engine_module._build_url(driver="psycopg"))

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "hunter2"


def test_missing_password_is_rejected(monkeypatch) -> None:
    _set_password(monkeypatch, None)

    try:
        engine_module._build_url()
    except ValueError as exc:
        assert "POSTGRES_AGENT_SERVICE_PASSWORD" in str(exc)
    else:
        raise AssertionError("expected a ValueError for the unset password")


def test_startup_connect_password_is_unmasked(monkeypatch) -> None:
    _set_password(monkeypatch, "hunter2")

    assert (
        startup_module._require_secret(
            env.POSTGRES_AGENT_SERVICE_PASSWORD, "POSTGRES_AGENT_SERVICE_PASSWORD"
        )
        == "hunter2"
    )
