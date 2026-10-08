"""Record parsing for file-based sources (S3, MinIO, GCS, R2, local uploads).

Structured formats (``csv``, ``jsonl``, ``json``) yield one record per row; a
``.tsv`` file is ``csv`` split on tabs unless a delimiter is configured.
``text`` yields a single record holding the whole document, which is what a
RAG pipeline wants for ``.txt`` / ``.md`` / ``.html`` files.
"""

from __future__ import annotations

import csv
import fnmatch
import io
import json
from collections.abc import Iterator
from typing import Any, BinaryIO, Literal

from .text import html_to_text

FileFormat = Literal["csv", "jsonl", "json", "text"]

EXT_TO_FORMAT: dict[str, FileFormat] = {
    ".csv": "csv",
    ".tsv": "csv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".json": "json",
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".rst": "text",
    ".html": "text",
    ".htm": "text",
    ".log": "text",
}


def parse_records(
    reader: BinaryIO,
    fmt: FileFormat,
    *,
    encoding: str = "utf-8",
    csv_delimiter: str = ",",
    name: str = "",
) -> Iterator[dict[str, Any]]:
    """Yield dict records from an open binary stream."""
    text = io.TextIOWrapper(reader, encoding=encoding, newline="", errors="replace")
    if fmt == "csv":
        for row in csv.DictReader(text, delimiter=csv_delimiter_for(name, csv_delimiter)):
            yield {k: v for k, v in row.items() if k is not None}
    elif fmt == "jsonl":
        for line in text:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                yield data
    elif fmt == "json":
        data = json.load(text)
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item
    else:  # text
        content = text.read()
        if name.lower().endswith((".html", ".htm")):
            content = html_to_text(content)
        yield {"content": content}


def csv_delimiter_for(name: str, configured: str = ",") -> str:
    """The column delimiter of the file ``name``.

    ``configured`` is the stream's setting, whose default ``,`` is right for ``.csv``
    files. A ``.tsv`` file left at that default is split on tabs, so one stream over
    mixed files needs no per-file setting; any other value is used as given.
    """
    if configured == "," and name.lower().endswith(".tsv"):
        return "\t"
    return configured


CHECKPOINT_FILES = 25
"""A file-by-file read (oldest first) saves its position about this often."""


def glob_match(rel_key: str, pattern: str) -> bool:
    """``fnmatch`` on a relative path; ``**`` / ``**/*`` / empty match everything."""
    if pattern in ("**", "**/*", "*", ""):
        return True
    if fnmatch.fnmatchcase(rel_key, pattern):
        return True
    # "**/" prefix: also match keys at the top level
    if pattern.startswith("**/"):
        return fnmatch.fnmatchcase(rel_key, pattern[3:])
    return False
