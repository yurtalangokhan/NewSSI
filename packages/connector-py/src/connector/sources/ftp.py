"""FTP / FTPS source: files over FTP, optionally with explicit TLS (standard library only).

Listing prefers ``MLSD`` (machine-readable, gives type, size and UTC
modification time). Servers without it fall back to ``NLST`` plus ``SIZE`` /
``MDTM`` per entry; an entry whose ``SIZE`` fails is treated as a directory.
"""

from __future__ import annotations

import contextlib
import ftplib
import io
import posixpath
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from ..base import secret_field
from ..common.file_system import FileEntry, FileSelectionOptions, FileSystemSource
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class FtpConfig(FileSelectionOptions):
    host: str
    port: int = 21
    username: str = "anonymous"
    password: str = secret_field(default="")
    paths: list[str] = Field(default_factory=lambda: ["/"], description="Folders to read.")
    tls: bool = Field(default=False, description="Explicit FTPS (AUTH TLS).")
    passive: bool = True
    server_encoding: str = Field(default="utf-8", description="Encoding of file names.")
    timeout_seconds: float = 60.0


class FtpFileSystem:
    def __init__(self, config: FtpConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client
        self._mlsd = True

    def _ftp(self) -> Any:
        if self._client is None:
            c = self._config
            client: ftplib.FTP = ftplib.FTP_TLS() if c.tls else ftplib.FTP()
            client.encoding = c.server_encoding
            client.connect(c.host, c.port, timeout=c.timeout_seconds)
            client.login(c.username, c.password)
            if c.tls:
                client.prot_p()  # type: ignore[attr-defined]
            client.set_pasv(c.passive)
            self._client = client
        return self._client

    def list_dir(self, path: str) -> list[FileEntry]:
        ftp = self._ftp()
        if self._mlsd:
            try:
                return self._list_mlsd(ftp, path)
            except ftplib.error_perm as exc:
                if not str(exc).startswith(("500", "501", "502")):
                    raise
                self._mlsd = False  # command not understood: use the legacy path from now on
        return self._list_legacy(ftp, path)

    @staticmethod
    def _list_mlsd(ftp: Any, path: str) -> list[FileEntry]:
        entries = []
        for name, facts in ftp.mlsd(path, facts=["type", "size", "modify"]):
            kind = (facts.get("type") or "").lower()
            if name in (".", "..") or kind in ("cdir", "pdir"):
                continue
            entries.append(
                FileEntry(
                    path=posixpath.join(path, name),
                    size=int(facts.get("size") or 0),
                    modified=_parse_mdtm(facts.get("modify")),
                    is_dir=kind == "dir",
                )
            )
        return entries

    @staticmethod
    def _list_legacy(ftp: Any, path: str) -> list[FileEntry]:
        entries = []
        for raw in ftp.nlst(path):
            full = raw if raw.startswith("/") else posixpath.join(path, raw)
            if posixpath.basename(full) in (".", ".."):
                continue
            try:
                size = ftp.size(full)
            except ftplib.error_perm:
                entries.append(FileEntry(path=full, is_dir=True))
                continue
            modified = None
            with contextlib.suppress(*ftplib.all_errors):  # MDTM is optional
                modified = _parse_mdtm(ftp.sendcmd(f"MDTM {full}").split()[-1])
            entries.append(FileEntry(path=full, size=int(size or 0), modified=modified))
        return entries

    def read_bytes(self, path: str) -> bytes:
        buffer = io.BytesIO()
        self._ftp().retrbinary(f"RETR {path}", buffer.write)
        return buffer.getvalue()

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.quit()
            except ftplib.all_errors:
                self._client.close()
            self._client = None


def _parse_mdtm(value: str | None) -> datetime | None:
    """``YYYYMMDDHHMMSS[.sss]`` in UTC, as defined by RFC 3659."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


class FtpSource(FileSystemSource[FtpConfig]):
    definition = ConnectorDefinition(
        name="ftp",
        display_name="FTP / FTPS",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.FILE,
        documentation_url="https://datatracker.ietf.org/doc/html/rfc959",
        icon="ftp.svg",
        tags=frozenset({"file", "ftp", "self-hosted"}),
    )
    Config = FtpConfig

    def roots(self) -> list[str]:
        return list(self.config.paths)

    def open_file_system(self) -> FtpFileSystem:
        return FtpFileSystem(self.config)

    def uri_for(self, path: str) -> str:
        scheme = "ftps" if self.config.tls else "ftp"
        return f"{scheme}://{self.config.host}:{self.config.port}{path}"
