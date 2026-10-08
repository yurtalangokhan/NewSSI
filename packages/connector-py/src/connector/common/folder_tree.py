"""Breadth-first folder walking for file stores without a recursive listing
(Box, Egnyte).

A connector describes one stream whose request lists a *single* folder and
implements two small hooks: how to address a folder and how to tell folders
from files in a listing. The walk reuses the declarative page engine, so
pagination, retries and transforms behave like any other stream.
"""

from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Mapping
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel

from .declarative import DeclarativeRestSource, StreamSpec, logger

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class FolderTreeSource(DeclarativeRestSource[ConfigT]):
    tree_stream: ClassVar[str] = "files"
    max_folders: ClassVar[int] = 100_000

    def root_folders(self) -> list[Any]:
        """Folder references (ids or paths) where the walk starts."""
        raise NotImplementedError

    def folder_spec(self, spec: StreamSpec, folder: Any) -> StreamSpec:
        """Return ``spec`` addressed at ``folder``."""
        raise NotImplementedError

    def subfolder(self, item: dict[str, Any]) -> Any | None:
        """Folder reference if ``item`` is a folder, else ``None``."""
        raise NotImplementedError

    def _already_seen(self, spec: StreamSpec, rec: Mapping[str, Any], cursor: Any) -> bool:
        # A folder's own modification time says nothing about what is inside it (Box
        # and Egnyte touch the direct parent at most): the walk descends regardless
        # of the cursor, and only files are filtered.
        if spec.name == self.tree_stream and self.subfolder(dict(rec)) is not None:
            return False
        return super()._already_seen(spec, rec, cursor)

    async def _read_records(self, spec: StreamSpec, cursor: Any) -> AsyncIterator[dict[str, Any]]:
        if spec.name != self.tree_stream:
            async for rec in super()._read_records(spec, cursor):
                yield rec
            return
        queue: deque[Any] = deque(self.root_folders())
        seen: set[str] = {str(f) for f in queue}
        visited = 0
        while queue and visited < self.max_folders:
            folder = queue.popleft()
            visited += 1
            try:
                async for item in self._read_pages(self.folder_spec(spec, folder), None, cursor):
                    child = self.subfolder(item)
                    if child is None:
                        yield item
                    elif str(child) not in seen:
                        seen.add(str(child))
                        queue.append(child)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in spec.skip_statuses:
                    raise
                logger.warning(
                    "%s: skipping folder %s (%s)", spec.name, folder, exc.response.status_code
                )
