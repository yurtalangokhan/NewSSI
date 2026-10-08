"""Vector hits must be identified by their chunk, not by their file.

langchain_community's ``Milvus._parse_document`` keeps only the text and the
metadata field, so a search result lost its primary key and callers fell back
to ``metadata.file_id``. Every chunk of a file then shared one identity: the
knowledge search fused all of a paper's chunks into one card with a summed
RRF score, which flattened every other hit's relevance to a few percent.
"""

from __future__ import annotations

from src.shared.vectorstore import chunk_id_milvus_class


def _store():
    store = object.__new__(chunk_id_milvus_class())
    store._primary_field = "pk"
    store._text_field = "text"
    store._metadata_field = "metadata"
    return store


def test_parsed_search_row_keeps_the_primary_key_as_document_id():
    document = _store()._parse_document(
        {"pk": 461218, "text": "chunk text", "metadata": {"file_id": "file-1"}}
    )

    assert document.id == "461218"
    assert document.page_content == "chunk text"
    assert document.metadata == {"file_id": "file-1"}


def test_row_without_a_primary_key_leaves_the_id_unset():
    document = _store()._parse_document({"text": "chunk text", "metadata": {}})

    assert document.id is None


def test_library_still_exposes_the_private_hook_the_subclass_overrides():
    from langchain_community.vectorstores import Milvus

    base = Milvus._parse_document
    override = chunk_id_milvus_class()._parse_document

    assert callable(base)
    assert override is not base
