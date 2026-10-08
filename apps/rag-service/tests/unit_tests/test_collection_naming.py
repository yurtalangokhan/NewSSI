from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from src.collections.naming import (
    collection_connector_type,
    collection_display_name,
    collection_sync_status,
)

if TYPE_CHECKING:
    from src.collections.schemas import CollectionDetails

UUID = "0123456789abcdef"


def _collection(title: str, **metadata: object) -> CollectionDetails:
    return {"uuid": UUID, "name": title, "metadata": dict(metadata)}


@pytest.mark.parametrize(
    ("collection", "expected"),
    [
        (_collection("raw", friendly_name=" Legal "), "Legal"),
        (_collection("raw", name="From metadata"), "From metadata"),
        (_collection("Contracts"), "Contracts"),
        (_collection("Unnamed"), "datasource-01234567"),
        (_collection("datasource label"), "datasource-01234567"),
        (_collection("  "), "datasource-01234567"),
    ],
)
def test_collection_display_name(collection: CollectionDetails, expected: str) -> None:
    assert collection_display_name(collection) == expected


def test_display_name_tolerates_missing_metadata() -> None:
    collection: CollectionDetails = {
        "uuid": UUID,
        "name": "Plain",
        "metadata": None,  # type: ignore[typeddict-item]
    }

    assert collection_display_name(collection) == "Plain"
    assert collection_connector_type(collection) == ""
    assert collection_sync_status(collection) == "idle"


def test_connector_type_and_sync_status_come_from_metadata() -> None:
    collection = _collection(
        "Drive", connector_type="google-drive", sync_status="running"
    )

    assert collection_connector_type(collection) == "google-drive"
    assert collection_sync_status(collection) == "running"
