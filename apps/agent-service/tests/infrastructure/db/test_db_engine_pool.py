"""The SQLAlchemy pool must retain connections, not churn them.

``POSTGRES_MIN_CONNECTIONS_PER_POOL`` / ``POSTGRES_MAX_CONNECTIONS_PER_POOL``
are psycopg_pool settings whose names mean "keep between N and M". Feeding them
to SQLAlchemy's ``pool_size`` / ``max_overflow`` means something else entirely:
``max_overflow`` connections are *disposable* and closed the moment they are
returned. With the shipped defaults (2 / 20) steady state retained only two
connections and every burst beyond that opened and closed a fresh TCP
connection — the reconnect churn this module guards against.

The pool is configured through ``config_manager.env``, whose getters read the
process environment on every access. These tests therefore patch environment
variables, and the engine sees them because it is built after the patch.
"""

from __future__ import annotations

import pytest


def _engine_kwargs(monkeypatch) -> dict:
    """Capture the kwargs ``get_db_engine`` hands to ``create_async_engine``."""
    import infrastructure.db.engine as engine_module

    captured: dict = {}

    def _fake_create(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(engine_module, "create_async_engine", _fake_create)
    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setattr(engine_module, "_session_factory", None)
    engine_module.get_db_engine()
    return captured


def test_pool_is_sized_from_dedicated_settings_not_the_psycopg_ones(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "99")
    monkeypatch.setenv("POSTGRES_MAX_OVERFLOW", "7")
    # The psycopg_pool values must not leak into the SQLAlchemy pool.
    monkeypatch.setenv("POSTGRES_MIN_CONNECTIONS_PER_POOL", "2")
    monkeypatch.setenv("POSTGRES_MAX_CONNECTIONS_PER_POOL", "20")

    kwargs = _engine_kwargs(monkeypatch)

    assert kwargs["pool_size"] == 99
    assert kwargs["max_overflow"] == 7


def test_pool_retains_more_than_the_legacy_default_of_two(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "10")

    kwargs = _engine_kwargs(monkeypatch)

    assert kwargs["pool_size"] > 2


def test_pool_timeout_and_lifo_are_configured(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_POOL_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("POSTGRES_POOL_USE_LIFO", "true")

    kwargs = _engine_kwargs(monkeypatch)

    assert kwargs["pool_timeout"] == 12.5
    assert kwargs["pool_use_lifo"] is True
    assert kwargs["pool_pre_ping"] is True


def test_connect_args_carry_command_timeout_and_application_name(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_COMMAND_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("POSTGRES_APPLICATION_NAME", "agent-service")

    kwargs = _engine_kwargs(monkeypatch)

    assert kwargs["connect_args"]["command_timeout"] == 42
    assert kwargs["connect_args"]["server_settings"]["application_name"] == "agent-service"


def test_pool_validation_rejects_nonsense(monkeypatch) -> None:
    import infrastructure.db.engine as engine_module

    monkeypatch.setattr(engine_module, "_engine", None)
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "0")

    with pytest.raises(ValueError, match="POSTGRES_POOL_SIZE"):
        engine_module.get_db_engine()


def test_pool_status_reports_checked_out_and_idle(monkeypatch) -> None:
    import infrastructure.db.engine as engine_module

    class _Pool:
        def status(self) -> str:
            return "Pool size: 10  Connections in pool: 2 Current Overflow: 1"

        def checkedout(self) -> int:
            return 3

        def checkedin(self) -> int:
            return 2

        def overflow(self) -> int:
            return 1

        def size(self) -> int:
            return 10

    class _Engine:
        pool = _Pool()

    monkeypatch.setattr(engine_module, "_engine", _Engine())

    status = engine_module.get_pool_status()

    assert status["size"] == 10
    assert status["checked_out"] == 3
    assert status["checked_in"] == 2
    assert status["overflow"] == 1
    assert "Pool size" in status["summary"]


def test_pool_status_is_safe_before_the_engine_exists(monkeypatch) -> None:
    import infrastructure.db.engine as engine_module

    monkeypatch.setattr(engine_module, "_engine", None)

    assert engine_module.get_pool_status() == {}
