"""Shared constrained argument types.

Putting the bound in the schema removes a whole class of parameter
pollution before any runtime check runs: an out-of-range value is a
validation error at the MCP boundary, not a value a tool function ever
has to defend against. See spec TS-9.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .sandbox import MAX_TIMEOUT_SECONDS

#: Most collections one knowledge search may name; the trusted binding is not
#: bounded by this, so the search service also caps its own concurrency.
MAX_COLLECTION_IDS = 20

BoundedTimeout = Annotated[int, Field(ge=1, le=int(MAX_TIMEOUT_SECONDS))]
BoundedLimit = Annotated[int, Field(ge=1, le=1000)]
BoundedPage = Annotated[int, Field(ge=1, le=10_000)]
ShortText = Annotated[str, Field(min_length=1, max_length=4096)]
LongText = Annotated[str, Field(max_length=1_000_000)]
GlobPattern = Annotated[str, Field(max_length=128)]
BoundedCollectionIds = Annotated[list[str], Field(max_length=MAX_COLLECTION_IDS)]
