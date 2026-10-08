"""File upload source: files that were uploaded to (or mounted into) a local directory.

Shares the file-tree reader with the FTP, SFTP and file server sources
(:mod:`connector.common.file_system`); only the transport is the local disk.
Binary files (PDF, Office, images) yield a metadata record carrying the
``absolute_path`` so a document-processing step can extract the text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from ..common.file_system import (
    FileEntry,
    FileSelectionOptions,
    FileSystemSource,
    LocalFileSystem,
    RemoteFileSystem,
)
from ..models import ConnectorCategory, ConnectorDefinition, ConnectorKind


class FileUploadConfig(FileSelectionOptions):
    directory: str = Field(description="Directory that receives the uploads.")


class FileUploadSource(FileSystemSource[FileUploadConfig]):
    definition = ConnectorDefinition(
        name="file_upload",
        display_name="File Upload",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.FILE,
        icon="file_upload.svg",
        tags=frozenset({"file", "local", "upload"}),
    )
    Config = FileUploadConfig

    def roots(self) -> list[str]:
        return [self.config.directory.replace("\\", "/")]

    def open_file_system(self) -> RemoteFileSystem:
        return LocalFileSystem()

    def uri_for(self, path: str) -> str:
        return Path(path).resolve().as_uri()

    def binary_extra(self, entry: FileEntry) -> dict[str, Any]:
        return {"absolute_path": str(Path(entry.path).resolve())}
