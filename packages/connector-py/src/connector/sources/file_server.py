"""File server source: a Windows / Samba share over SMB, or a mounted network path.

Two ways to reach the share:

* ``mount_path`` - the share (SMB, NFS, DFS ...) is already mounted on the host or
  in the container; it is read like any local directory. No extra dependency.
* ``server`` + ``share`` - connect over SMB 2/3 directly with ``smbprotocol``
  (``pip install connector-py[smb]``). Useful in containers where mounting
  needs privileges.
"""

from __future__ import annotations

import contextlib
import stat as stat_module
from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator

from ..base import secret_field
from ..common.file_system import (
    FileEntry,
    FileSelectionOptions,
    FileSystemSource,
    LocalFileSystem,
    RemoteFileSystem,
)
from ..extras import require_extra
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class FileServerConfig(FileSelectionOptions):
    mount_path: str | None = Field(
        default=None, description="Local mount point of the share, e.g. /mnt/fileserver."
    )
    server: str | None = Field(default=None, description="SMB host name or IP.")
    share: str | None = Field(default=None, description="Share name, e.g. 'Departments'.")
    port: int = 445
    username: str | None = Field(default=None, description="DOMAIN\\\\user or user@domain.")
    password: str | None = secret_field(default=None)
    paths: list[str] = Field(
        default_factory=lambda: ["/"], description="Folders inside the share / mount to read."
    )
    encrypt: bool = Field(default=False, description="Require SMB3 encryption.")
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _target(self) -> FileServerConfig:
        if not self.mount_path and not (self.server and self.share):
            raise ValueError("provide mount_path, or server and share")
        return self


class SmbFileSystem:
    r"""Paths are share-relative with ``/``; they are mapped to ``\\server\share\...``."""

    def __init__(self, config: FileServerConfig, smbclient: Any | None = None) -> None:
        self._config = config
        self._smb = smbclient
        self._registered = False

    def _client(self) -> Any:
        if self._smb is None:
            self._smb = require_extra("smbclient", extra="smb", feature="SMB access")
        if not self._registered:
            c = self._config
            self._smb.register_session(
                c.server,
                username=c.username,
                password=c.password,
                port=c.port,
                encrypt=c.encrypt,
                connection_timeout=c.timeout_seconds,
            )
            self._registered = True
        return self._smb

    def _unc(self, path: str) -> str:
        tail = path.strip("/").replace("/", "\\")
        base = f"\\\\{self._config.server}\\{self._config.share}"
        return f"{base}\\{tail}" if tail else base

    def list_dir(self, path: str) -> list[FileEntry]:
        entries = []
        prefix = "/" + path.strip("/")
        for item in self._client().scandir(self._unc(path)):
            info = item.stat()
            entries.append(
                FileEntry(
                    path=f"{prefix.rstrip('/')}/{item.name}",
                    size=int(info.st_size or 0),
                    modified=datetime.fromtimestamp(info.st_mtime, tz=UTC),
                    is_dir=stat_module.S_ISDIR(info.st_mode),
                )
            )
        return entries

    def read_bytes(self, path: str) -> bytes:
        with self._client().open_file(self._unc(path), mode="rb") as fh:
            return fh.read()

    def close(self) -> None:
        if self._smb is not None and self._registered:
            with contextlib.suppress(Exception):  # best effort cleanup
                self._smb.delete_session(self._config.server, port=self._config.port)
            self._registered = False


class FileServerSource(FileSystemSource[FileServerConfig]):
    definition = ConnectorDefinition(
        name="file_server",
        display_name="File Server (SMB / network share)",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.FILE,
        documentation_url="https://github.com/jborean93/smbprotocol",
        icon="file_server.svg",
        tags=frozenset({"file", "smb", "nfs", "self-hosted"}),
    )
    Config = FileServerConfig

    def roots(self) -> list[str]:
        if self.config.mount_path:
            base = self.config.mount_path.replace("\\", "/").rstrip("/")
            return [f"{base}/{p.strip('/')}".rstrip("/") or base for p in self.config.paths]
        return list(self.config.paths)

    def open_file_system(self) -> RemoteFileSystem:
        return LocalFileSystem() if self.config.mount_path else SmbFileSystem(self.config)

    def uri_for(self, path: str) -> str:
        if self.config.mount_path:
            return f"file://{path}"
        return f"smb://{self.config.server}/{self.config.share}/{path.strip('/')}"
