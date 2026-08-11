from __future__ import annotations


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from langconnect.database.postgres import startup

    events: list[str] = []
    options: dict[str, str] = {}
    logs: list[tuple[str, tuple[object, ...]]] = []

    class FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path
            self.attributes = {}

        def set_main_option(self, key: str, value: str) -> None:
            options[key] = value

    monkeypatch.setattr(
        startup, "ensure_database_exists", lambda: events.append("ensure")
    )
    monkeypatch.setattr(startup, "Config", FakeConfig)
    monkeypatch.setattr(
        startup.command,
        "upgrade",
        lambda config, revision: events.append(f"upgrade:{revision}"),
    )
    revision_states = iter([("0002", "0003"), ("0003", "0003")])
    monkeypatch.setattr(
        startup, "_migration_revision_state", lambda config: next(revision_states)
    )
    monkeypatch.setattr(
        startup.logger,
        "info",
        lambda message, *args: logs.append((message, args)),
    )

    startup.run_startup_migrations()

    assert events == ["ensure", "upgrade:head"]
    assert options["script_location"].endswith(
        "apps/rag-service/langconnect/database/postgres/migrations"
    )
    assert options["prepend_sys_path"].endswith("apps/rag-service")
    assert startup._build_alembic_config().attributes["configure_logger"] is False
    assert (
        "LangConnect database migration check: current=%s target=%s",
        ("0002", "0003"),
    ) in logs
    assert (
        "LangConnect database migrations completed: current=%s target=%s",
        ("0003", "0003"),
    ) in logs
