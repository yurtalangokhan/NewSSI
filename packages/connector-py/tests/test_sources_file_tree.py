"""FTP, SFTP and file server sources: the shared reader plus each transport adapter."""

from __future__ import annotations

import ftplib
import io
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from connector import ConfigValidationError
from connector.common.file_system import FileEntry
from connector.sources.file_server import FileServerSource, SmbFileSystem
from connector.sources.ftp import FtpConfig, FtpFileSystem, FtpSource
from connector.sources.sftp import SftpFileSystem, SftpSource, fingerprint_sha256
from tests.fake_api import read_all

T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 1, 2, tzinfo=UTC)
T3 = datetime(2026, 1, 3, tzinfo=UTC)


class FakeFileSystem:
    """In-memory tree: ``{path: (bytes, modified)}``; folders are implied by the paths."""

    def __init__(self, files: dict[str, tuple[bytes, datetime]]) -> None:
        self.files = files
        self.read_calls: list[str] = []
        self.closed = False

    def list_dir(self, path: str) -> list[FileEntry]:
        base = path.rstrip("/") + "/"
        if not any(p.startswith(base) for p in self.files):
            raise FileNotFoundError(path)
        seen: dict[str, FileEntry] = {}
        for full, (data, modified) in self.files.items():
            if not full.startswith(base):
                continue
            head, _, rest = full[len(base) :].partition("/")
            child = base + head
            seen[child] = (
                FileEntry(path=child, is_dir=True)
                if rest
                else FileEntry(path=child, size=len(data), modified=modified)
            )
        return list(seen.values())

    def read_bytes(self, path: str) -> bytes:
        self.read_calls.append(path)
        return self.files[path][0]

    def close(self) -> None:
        self.closed = True


TREE = {
    "/data/orders.csv": (b"id,total\n1,9.5\n", T1),
    "/data/docs/guide.md": (b"# Guide", T2),
    "/data/docs/deep/scan.pdf": (b"%PDF", T3),
    "/data/docs/big.txt": (b"x" * 500, T3),
    "/other/skip.txt": (b"no", T3),
}


# ---------------------------------------------------------------------------
# shared reader (through the FTP source)
# ---------------------------------------------------------------------------


async def test_reader_walks_parses_and_reports_binary_metadata() -> None:
    fs = FakeFileSystem(TREE)
    cfg = {"host": "ftp.test", "paths": ["/data"], "max_file_size_bytes": 100}
    src = FtpSource(FtpSource.validate_config(cfg), fs_factory=lambda c: fs)
    assert (await src.check()).ok
    records, _ = await read_all(src)
    by_file = {r["_source_file"]: r for r in records["files"]}
    assert set(by_file) == {"orders.csv", "docs/guide.md", "docs/deep/scan.pdf"}  # big.txt skipped
    assert by_file["orders.csv"]["total"] == "9.5"
    assert by_file["docs/guide.md"]["content"] == "# Guide"
    assert by_file["docs/guide.md"]["_source_uri"] == "ftp://ftp.test:21/data/docs/guide.md"
    pdf = by_file["docs/deep/scan.pdf"]
    assert pdf["binary"] is True and pdf["mime_type"] == "application/pdf" and pdf["size"] == 4
    assert "/data/docs/deep/scan.pdf" not in fs.read_calls  # binaries are never downloaded
    assert fs.closed


async def test_reader_glob_non_recursive_and_incremental_cursor() -> None:
    fs = FakeFileSystem(TREE)
    flat = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/data"], "recursive": False}),
        fs_factory=lambda c: fs,
    )
    records, _ = await read_all(flat)
    assert [r["_source_file"] for r in records["files"]] == ["orders.csv"]

    only_md = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/data"], "glob": "**/*.md"}),
        fs_factory=lambda c: fs,
    )
    records, states = await read_all(only_md, incremental=True)
    assert [r["_source_file"] for r in records["files"]] == ["docs/guide.md"]
    assert states["files"] == {"cursor": T2.isoformat(), "keys_at_cursor": ["/data/docs/guide.md"]}

    everything = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/data"]}), fs_factory=lambda c: fs
    )
    newer, states = await read_all(everything, incremental=True, state=states)
    assert sorted(r["_source_file"] for r in newer["files"]) == [
        "docs/big.txt",
        "docs/deep/scan.pdf",
    ]
    assert states["files"] == {
        "cursor": T3.isoformat(),
        "keys_at_cursor": ["/data/docs/big.txt", "/data/docs/deep/scan.pdf"],
    }


async def test_reader_incremental_reads_files_written_in_the_cursor_second_later() -> None:
    tree = {"/data/a.txt": (b"a", T2), "/data/b.txt": (b"b", T2)}
    fs = FakeFileSystem(tree)
    src = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/data"]}), fs_factory=lambda c: fs
    )
    records, states = await read_all(src, incremental=True)
    assert sorted(r["_source_file"] for r in records["files"]) == ["a.txt", "b.txt"]
    assert states["files"] == {
        "cursor": T2.isoformat(),
        "keys_at_cursor": ["/data/a.txt", "/data/b.txt"],
    }
    tree["/data/c.txt"] = (b"c", T2)  # written in the cursor's second, after the listing
    records, states = await read_all(src, incremental=True, state=states)
    assert [r["_source_file"] for r in records["files"]] == ["c.txt"]
    assert states["files"]["keys_at_cursor"] == ["/data/a.txt", "/data/b.txt", "/data/c.txt"]
    # A state written before the keys were recorded skips the cursor second, as it did.
    legacy = {"files": {"cursor": T2.isoformat()}}
    records, _ = await read_all(src, incremental=True, state=legacy)
    assert records == {}


async def test_the_file_cap_counts_what_a_sync_reads_not_what_it_already_has() -> None:
    def note(day: int) -> tuple[bytes, datetime]:
        return (b"note", datetime(2026, 1, day, tzinfo=UTC))

    tree = {
        f"/data/{name}.txt": note(day) for name, day in (("a", 1), ("b", 2), ("c", 3), ("d", 4))
    }
    # Two files share the latest time: a cut between them would leave one behind for
    # good, because the cursor is that time.
    tree["/data/e.txt"] = note(4)
    src = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/data"], "max_files": 2}),
        fs_factory=lambda c: FakeFileSystem(tree),
    )

    runs: list[list[str]] = []
    states: dict[str, Any] = {}
    for _ in range(4):
        records, new_states = await read_all(src, incremental=True, state=states)
        runs.append([r["_source_file"] for r in records.get("files", [])])
        states = {**states, **new_states}

    # Each run takes the next files; the cap is not spent on the ones already read.
    assert runs == [["a.txt", "b.txt"], ["c.txt", "d.txt", "e.txt"], [], []]
    assert states["files"] == {
        "cursor": datetime(2026, 1, 4, tzinfo=UTC).isoformat(),
        "keys_at_cursor": ["/data/d.txt", "/data/e.txt"],
    }

    # A full refresh reads the oldest ``max_files`` files, as before.
    records, _ = await read_all(src)
    assert [r["_source_file"] for r in records["files"]] == ["a.txt", "b.txt"]


async def test_check_reports_a_missing_folder() -> None:
    src = FtpSource(
        FtpSource.validate_config({"host": "h", "paths": ["/nope"]}),
        fs_factory=lambda c: FakeFileSystem(TREE),
    )
    result = await src.check()
    assert not result.ok and "FileNotFoundError" in (result.message or "")


# ---------------------------------------------------------------------------
# FTP adapter
# ---------------------------------------------------------------------------


class _FakeFtp:
    def __init__(self, *, mlsd: bool) -> None:
        self._mlsd = mlsd
        self.quit_called = False

    def mlsd(self, path: str, facts: list[str]) -> list[tuple[str, dict[str, str]]]:
        if not self._mlsd:
            raise ftplib.error_perm("500 Unknown command")
        return [
            (".", {"type": "cdir"}),
            ("reports", {"type": "dir"}),
            ("a.csv", {"type": "file", "size": "12", "modify": "20260102030405.123"}),
        ]

    def nlst(self, path: str) -> list[str]:
        return ["reports", "a.csv"]

    def size(self, path: str) -> int:
        if path.endswith("reports"):
            raise ftplib.error_perm("550 not a plain file")
        return 12

    def sendcmd(self, command: str) -> str:
        assert command == "MDTM /in/a.csv"
        return "213 20260102030405"

    def retrbinary(self, command: str, callback: Any) -> None:
        assert command == "RETR /in/a.csv"
        callback(b"id\n1\n")

    def quit(self) -> None:
        self.quit_called = True


@pytest.mark.parametrize("mlsd", [True, False], ids=["mlsd", "legacy-nlst"])
def test_ftp_adapter_lists_and_downloads(mlsd: bool) -> None:
    client = _FakeFtp(mlsd=mlsd)
    fs = FtpFileSystem(FtpConfig(host="h"), client=client)
    entries = {e.name: e for e in fs.list_dir("/in")}
    assert entries["reports"].is_dir and not entries["a.csv"].is_dir
    assert entries["a.csv"].size == 12
    assert entries["a.csv"].modified == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert fs.read_bytes("/in/a.csv") == b"id\n1\n"
    fs.close()
    assert client.quit_called


def test_ftp_other_permission_errors_are_not_swallowed() -> None:
    class Denied(_FakeFtp):
        def mlsd(self, path: str, facts: list[str]) -> Any:
            raise ftplib.error_perm("550 Permission denied")

    with pytest.raises(ftplib.error_perm):
        FtpFileSystem(FtpConfig(host="h"), client=Denied(mlsd=True)).list_dir("/in")


def test_ftps_uri_and_password_is_secret() -> None:
    src = FtpSource.from_config({"host": "h", "tls": True, "port": 990})
    assert src.uri_for("/a.txt") == "ftps://h:990/a.txt"
    assert FtpSource.secret_fields() == {"password"}


# ---------------------------------------------------------------------------
# SFTP adapter
# ---------------------------------------------------------------------------


class _FakeSftp:
    def __init__(self) -> None:
        self.closed = False

    def listdir_attr(self, path: str) -> list[Any]:
        return [
            SimpleNamespace(filename="sub", st_mode=stat.S_IFDIR | 0o755, st_size=0, st_mtime=0),
            SimpleNamespace(
                filename="n.jsonl", st_mode=stat.S_IFREG | 0o644, st_size=9, st_mtime=1767312000
            ),
        ]

    def open(self, path: str, mode: str) -> io.BytesIO:
        assert (path, mode) == ("/up/n.jsonl", "rb")
        return io.BytesIO(b'{"id": 1}\n')

    def close(self) -> None:
        self.closed = True


def test_sftp_adapter_and_config_rules() -> None:
    cfg = SftpSource.validate_config({"host": "h", "username": "u", "password": "p"})
    client = _FakeSftp()
    fs = SftpFileSystem(cfg, client=client)
    entries = {e.name: e for e in fs.list_dir("/up")}
    assert entries["sub"].is_dir and entries["sub"].modified is None
    assert entries["n.jsonl"].modified == datetime(2026, 1, 2, tzinfo=UTC)
    assert fs.read_bytes("/up/n.jsonl") == b'{"id": 1}\n'
    fs.close()
    assert client.closed

    assert SftpSource.secret_fields() == {"password", "private_key", "private_key_passphrase"}
    assert SftpSource.from_config({"host": "h", "username": "u", "password": "p"}).uri_for(
        "/x"
    ) == ("sftp://h:22/x")
    with pytest.raises(ConfigValidationError):
        SftpSource.validate_config({"host": "h", "username": "u"})
    assert fingerprint_sha256(b"key").startswith("SHA256:") and "=" not in fingerprint_sha256(b"k")


def test_sftp_connects_with_a_timeout_and_closes_the_transport_when_auth_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``paramiko.Transport((host, port))`` connects without a timeout (minutes on a black
    # hole), and a failed login left the transport's thread and socket behind.
    from connector.sources import sftp as module

    connections: list[tuple[tuple[str, int], float | None]] = []
    transports: list[Any] = []

    def fake_create_connection(address: tuple[str, int], timeout: float | None = None) -> str:
        connections.append((address, timeout))
        return "sock"

    class _Transport:
        def __init__(self, sock: Any) -> None:
            self.sock, self.closed, self.banner_timeout = sock, False, None
            transports.append(self)

        def start_client(self, timeout: float | None = None) -> None:
            self.started = timeout

        def auth_password(self, username: str, password: str) -> None:
            raise RuntimeError("Authentication failed.")

        def close(self) -> None:
            self.closed = True

    fake_paramiko = SimpleNamespace(Transport=_Transport)
    monkeypatch.setattr(module, "require_extra", lambda *a, **k: fake_paramiko)
    monkeypatch.setattr(module.socket, "create_connection", fake_create_connection)

    cfg = SftpSource.validate_config(
        {"host": "h", "port": 2222, "username": "u", "password": "p", "timeout_seconds": 7}
    )
    fs = SftpFileSystem(cfg)
    with pytest.raises(RuntimeError, match="Authentication failed"):
        fs.list_dir("/")
    assert connections == [(("h", 2222), 7.0)]
    assert transports[0].sock == "sock" and transports[0].started == 7.0
    assert transports[0].closed


# ---------------------------------------------------------------------------
# file server: SMB adapter and mounted path
# ---------------------------------------------------------------------------


class _FakeSmb:
    def __init__(self) -> None:
        self.sessions: list[tuple[str, dict[str, Any]]] = []
        self.scanned: list[str] = []
        self.deleted = False

    def register_session(self, server: str, **kwargs: Any) -> None:
        self.sessions.append((server, kwargs))

    def scandir(self, unc: str) -> list[Any]:
        self.scanned.append(unc)

        def item(name: str, mode: int, size: int) -> Any:
            info = SimpleNamespace(st_size=size, st_mtime=1767312000, st_mode=mode)
            return SimpleNamespace(name=name, stat=lambda: info)

        return [item("HR", stat.S_IFDIR, 0), item("plan.txt", stat.S_IFREG, 4)]

    def open_file(self, unc: str, mode: str) -> io.BytesIO:
        assert unc == "\\\\fs01\\Departments\\Finance\\plan.txt" and mode == "rb"
        return io.BytesIO(b"plan")

    def delete_session(self, server: str, port: int) -> None:
        self.deleted = True


def test_smb_adapter_maps_paths_to_unc() -> None:
    cfg = FileServerSource.validate_config(
        {"server": "fs01", "share": "Departments", "username": "ACME\\svc", "password": "p"}
    )
    smb = _FakeSmb()
    fs = SmbFileSystem(cfg, smbclient=smb)
    entries = {e.name: e for e in fs.list_dir("/Finance")}
    assert smb.scanned == ["\\\\fs01\\Departments\\Finance"]
    assert entries["HR"].is_dir and entries["plan.txt"].path == "/Finance/plan.txt"
    assert fs.read_bytes("/Finance/plan.txt") == b"plan"
    fs.list_dir("/")
    assert smb.scanned[-1] == "\\\\fs01\\Departments" and len(smb.sessions) == 1
    assert smb.sessions[0][1]["username"] == "ACME\\svc"
    fs.close()
    assert smb.deleted


async def test_file_server_with_mount_path(tmp_path: Path) -> None:
    (tmp_path / "Finance").mkdir()
    report = tmp_path / "Finance" / "q1.md"
    report.write_text("# Q1", encoding="utf-8")
    os.utime(report, (1767312000, 1767312000))
    (tmp_path / "ignored.txt").write_text("root file outside the selected path", encoding="utf-8")

    cfg = {"mount_path": str(tmp_path), "paths": ["/Finance"]}
    src = FileServerSource.from_config(cfg)
    assert (await src.check()).ok
    records, states = await read_all(src, incremental=True)
    assert [(r["_source_file"], r["content"]) for r in records["files"]] == [("q1.md", "# Q1")]
    assert records["files"][0]["_source_uri"].startswith("file://")
    assert states["files"]["cursor"] == "2026-01-02T00:00:00+00:00"

    smb = FileServerSource.from_config({"server": "fs01", "share": "Dept"})
    assert smb.uri_for("/a/b.txt") == "smb://fs01/Dept/a/b.txt"
    with pytest.raises(ConfigValidationError):
        FileServerSource.validate_config({"server": "fs01"})
