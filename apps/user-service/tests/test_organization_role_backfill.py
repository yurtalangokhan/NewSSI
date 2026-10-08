import importlib
import sqlite3


def test_backfill_only_missing_valid_platform_assignments(monkeypatch):
    migration = importlib.import_module(
        "src.core.database.migrations.versions.0045_organization_platform_roles"
    )
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE users (id TEXT PRIMARY KEY, role TEXT);
        CREATE TABLE composite_roles (name TEXT PRIMARY KEY);
        CREATE TABLE user_roles (user_id TEXT, role_name TEXT, is_primary BOOLEAN, created_at TEXT, PRIMARY KEY(user_id, role_name));
        INSERT INTO composite_roles VALUES ('enduser'), ('Unit Manager');
        INSERT INTO users VALUES ('missing', 'enduser'), ('assigned', 'enduser'), ('invalid', 'unknown');
        INSERT INTO user_roles VALUES ('assigned', 'Unit Manager', 1, 'existing');
    """)
    monkeypatch.setattr(migration.op, "execute", lambda statement: db.execute(str(statement)))
    migration.upgrade()
    migration.upgrade()
    assert db.execute("SELECT user_id, role_name FROM user_roles ORDER BY user_id").fetchall() == [
        ("assigned", "Unit Manager"),
        ("missing", "enduser"),
    ]
    assert (
        db.execute("SELECT created_at FROM user_roles WHERE user_id='assigned'").fetchone()[0]
        == "existing"
    )
