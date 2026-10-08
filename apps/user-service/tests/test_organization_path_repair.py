import importlib
import sqlite3


def test_path_repair_preserves_parent_links_and_rebuilds_depth(monkeypatch):
    migration = importlib.import_module(
        "src.core.database.migrations.versions.0047_repair_organization_paths"
    )
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE organizations(id TEXT PRIMARY KEY, parent_id TEXT, path TEXT, level INTEGER);
        INSERT INTO organizations VALUES ('root', NULL, '/root/', 0),
        ('target', 'root', '/root/target/', 1),
        ('moved', 'target', '/root/target/target/', 2),
        ('child', 'moved', '/old/moved/child/', 2),
        ('grandchild', 'child', '/old/child/grandchild/', 2);
    """)
    monkeypatch.setattr(migration.op, "execute", lambda statement: db.execute(str(statement)))
    migration.upgrade()
    migration.upgrade()
    assert db.execute(
        "SELECT id,parent_id,path,level FROM organizations ORDER BY level"
    ).fetchall() == [
        ("root", None, "/", 0),
        ("target", "root", "/root/", 1),
        ("moved", "target", "/root/target/", 2),
        ("child", "moved", "/root/target/moved/", 3),
        ("grandchild", "child", "/root/target/moved/child/", 4),
    ]
