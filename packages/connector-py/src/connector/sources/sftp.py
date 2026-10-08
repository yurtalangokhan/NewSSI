"""SFTP source: files over SSH with password or private-key authentication.

Requires the ``sftp`` extra (paramiko).

Authenticates with a password or a private key (PEM text, optionally with a
passphrase). Set ``host_key_fingerprint`` (the ``SHA256:...`` value shown by
``ssh-keygen -lf``) to pin the server; without it the first key is accepted,
which is convenient but open to man-in-the-middle attacks.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import posixpath
import socket
import stat as stat_module
from datetime import UTC, datetime
from typing import Any

from pydantic import Field, model_validator

from ..base import secret_field
from ..common.file_system import FileEntry, FileSelectionOptions, FileSystemSource
from ..errors import SourceError
from ..extras import require_extra
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class SftpConfig(FileSelectionOptions):
    host: str
    port: int = 22
    username: str
    password: str | None = secret_field(default=None)
    private_key: str | None = secret_field(default=None, description="Private key in PEM format.")
    private_key_passphrase: str | None = secret_field(default=None)
    host_key_fingerprint: str | None = Field(
        default=None, description="Expected 'SHA256:...' fingerprint of the server key."
    )
    paths: list[str] = Field(default_factory=lambda: ["/"], description="Folders to read.")
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _credentials(self) -> SftpConfig:
        if not self.password and not self.private_key:
            raise ValueError("provide password or private_key")
        return self


def _load_private_key(pem: str, passphrase: str | None) -> Any:
    paramiko = require_extra("paramiko", extra="sftp", feature="sftp source")

    last: Exception | None = None
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(pem), password=passphrase)
        except paramiko.SSHException as exc:
            last = exc
    raise ValueError(f"unsupported or invalid private key: {last}")


def fingerprint_sha256(key_bytes: bytes) -> str:
    digest = base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


class SftpFileSystem:
    def __init__(self, config: SftpConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client
        self._transport: Any | None = None

    def _sftp(self) -> Any:
        if self._client is None:
            paramiko = require_extra("paramiko", extra="sftp", feature="sftp source")
            c = self._config
            # paramiko connects a bare address without a timeout; a socket of our own
            # gives the TCP connect the same limit as the rest of the handshake.
            sock = socket.create_connection((c.host, c.port), timeout=c.timeout_seconds)
            transport = paramiko.Transport(sock)
            transport.banner_timeout = c.timeout_seconds
            try:
                transport.start_client(timeout=c.timeout_seconds)
                if c.host_key_fingerprint:
                    actual = fingerprint_sha256(transport.get_remote_server_key().asbytes())
                    if actual != c.host_key_fingerprint:
                        raise SourceError(f"host key mismatch: server presented {actual}")
                if c.private_key:
                    key = _load_private_key(c.private_key, c.private_key_passphrase)
                    transport.auth_publickey(c.username, key)
                else:
                    transport.auth_password(c.username, c.password or "")
                self._client = paramiko.SFTPClient.from_transport(transport)
            except BaseException:
                # A refused login or a bad key must not leave the transport thread and
                # its socket behind.
                with contextlib.suppress(Exception):
                    transport.close()
                raise
            self._transport = transport
        return self._client

    def list_dir(self, path: str) -> list[FileEntry]:
        entries = []
        for attr in self._sftp().listdir_attr(path):
            if attr.filename in (".", ".."):
                continue
            mode = attr.st_mode or 0
            entries.append(
                FileEntry(
                    path=posixpath.join(path, attr.filename),
                    size=int(attr.st_size or 0),
                    modified=datetime.fromtimestamp(attr.st_mtime, tz=UTC)
                    if attr.st_mtime
                    else None,
                    is_dir=stat_module.S_ISDIR(mode),
                )
            )
        return entries

    def read_bytes(self, path: str) -> bytes:
        with self._sftp().open(path, "rb") as fh:
            return fh.read()

    def close(self) -> None:
        for resource in (self._client, self._transport):
            if resource is not None:
                with contextlib.suppress(Exception):  # best effort cleanup
                    resource.close()
        self._client = self._transport = None


class SftpSource(FileSystemSource[SftpConfig]):
    definition = ConnectorDefinition(
        name="sftp",
        display_name="SFTP",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.FILE,
        documentation_url="https://docs.paramiko.org/en/stable/api/sftp.html",
        icon="sftp.svg",
        tags=frozenset({"file", "ssh", "self-hosted"}),
    )
    Config = SftpConfig

    def roots(self) -> list[str]:
        return list(self.config.paths)

    def open_file_system(self) -> SftpFileSystem:
        return SftpFileSystem(self.config)

    def uri_for(self, path: str) -> str:
        return f"sftp://{self.config.host}:{self.config.port}{path}"
