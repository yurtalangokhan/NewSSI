"""One Milvus store per collection, not one per call.

``Collection._get_store`` called ``get_vectorstore`` on every single
operation, and constructing a ``Milvus`` store is not free: it registers a
connection alias, asks the server whether the collection exists and, when
it does, builds a ``Collection`` handle and loads its schema. Listing
documents, searching, upserting and deleting each paid that round-trip
before doing any actual work, and every construction registered another
connection.

A store whose collection does not exist yet (``col is None``) is
deliberately not cached: it would keep reporting an empty collection even
after the rows were written by something else.
"""

from __future__ import annotations

import pytest

from src.shared import vectorstore as connection


class _FakeMilvus:
    instances = 0

    def __init__(self, **kwargs: object) -> None:
        type(self).instances += 1
        self.kwargs = kwargs
        self.col = object()


@pytest.fixture(autouse=True)
def _reset() -> None:
    connection.clear_vectorstore_cache()
    _FakeMilvus.instances = 0
    yield
    connection.clear_vectorstore_cache()


@pytest.fixture
def milvus(monkeypatch: pytest.MonkeyPatch) -> type[_FakeMilvus]:
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "milvus")
    monkeypatch.setattr(
        connection, "_build_milvus_store", lambda name, emb, **kw: _FakeMilvus(**kw)
    )
    return _FakeMilvus


def test_the_same_collection_reuses_one_store(milvus):
    first = connection.get_vectorstore(collection_name="table-a")
    second = connection.get_vectorstore(collection_name="table-a")

    assert first is second
    assert milvus.instances == 1


def test_different_collections_get_different_stores(milvus):
    a = connection.get_vectorstore(collection_name="table-a")
    b = connection.get_vectorstore(collection_name="table-b")

    assert a is not b
    assert milvus.instances == 2


def test_a_collection_that_does_not_exist_yet_is_not_cached(monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "milvus")

    class _Uncreated(_FakeMilvus):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.col = None

    monkeypatch.setattr(
        connection, "_build_milvus_store", lambda name, emb, **kw: _Uncreated()
    )

    first = connection.get_vectorstore(collection_name="table-new")
    second = connection.get_vectorstore(collection_name="table-new")

    assert first is not second, "an empty, not-yet-created collection was cached"


def test_a_custom_embedding_is_never_served_from_the_cache(milvus):
    other = object()

    cached = connection.get_vectorstore(collection_name="table-a")
    custom = connection.get_vectorstore(collection_name="table-a", embeddings=other)

    assert custom is not cached


def test_index_params_are_forwarded_to_the_milvus_store(monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "milvus")
    captured: dict[str, object] = {}

    def _fake_build(name: str, emb: object, **kwargs: object) -> _FakeMilvus:
        captured.update(kwargs)
        return _FakeMilvus(**kwargs)

    monkeypatch.setattr(connection, "_build_milvus_store", _fake_build)

    connection.get_vectorstore(
        collection_name="table-cosine",
        index_params={"metric_type": "COSINE"},
        search_params={"metric_type": "COSINE"},
    )

    assert captured["index_params"] == {"metric_type": "COSINE"}
    assert captured["search_params"] == {"metric_type": "COSINE"}


def test_a_store_with_custom_index_params_is_not_cached_alongside_the_default(milvus):
    default = connection.get_vectorstore(collection_name="table-a")
    custom = connection.get_vectorstore(
        collection_name="table-a", index_params={"metric_type": "COSINE"}
    )

    assert custom is not default


def test_the_pgvector_path_is_untouched(monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PROVIDER", "pgvector")
    monkeypatch.setattr(
        connection,
        "_build_milvus_store",
        lambda name, emb, **kw: pytest.fail("wrong branch"),
    )
    built: list[object] = []

    class _FakePGVector:
        def __init__(self, **kwargs: object) -> None:
            built.append(self)

    monkeypatch.setattr(
        connection, "_build_pgvector_store", lambda **kw: _FakePGVector()
    )

    a = connection.get_vectorstore(collection_name="table-a", engine=object())
    b = connection.get_vectorstore(collection_name="table-a", engine=object())

    assert a is not b
    assert len(built) == 2
