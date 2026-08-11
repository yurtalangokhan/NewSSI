from __future__ import annotations


def test_run_startup_migrations_ensures_database_before_alembic(monkeypatch):
    from langconnect.database.postgres import startup

    events: list[str] = []

    monkeypatch.setattr(startup, "ensure_database_exists", lambda: events.append("ensure"))
    monkeypatch.setattr(startup, "Config", lambda path: f"config:{path}")
    monkeypatch.setattr(
        startup.command,
        "upgrade",
        lambda config, revision: events.append(f"upgrade:{revision}"),
    )

    startup.run_startup_migrations()

    assert events == ["ensure", "upgrade:head"]
