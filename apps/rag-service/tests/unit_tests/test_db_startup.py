from __future__ import annotations


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from langconnect.database.postgres import startup

    events: list[str] = []
    options: dict[str, str] = {}

    class FakeConfig:
        def __init__(self, path: str) -> None:
            self.path = path

        def set_main_option(self, key: str, value: str) -> None:
            options[key] = value

    monkeypatch.setattr(startup, "ensure_database_exists", lambda: events.append("ensure"))
    monkeypatch.setattr(startup, "Config", FakeConfig)
    monkeypatch.setattr(
        startup.command,
        "upgrade",
        lambda config, revision: events.append(f"upgrade:{revision}"),
    )

    startup.run_startup_migrations()

    assert events == ["ensure", "upgrade:head"]
    assert options["script_location"].endswith(
        "apps/rag-service/langconnect/database/postgres/migrations"
    )
    assert options["prepend_sys_path"].endswith("apps/rag-service")
