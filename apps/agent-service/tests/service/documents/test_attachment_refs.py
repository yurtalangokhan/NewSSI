from __future__ import annotations

from service.documents.attachment_refs import ATTACHMENT_SCHEME, attachment_image_ids, attachment_ref


def test_attachment_ref_extracts_the_file_id():
    assert attachment_ref("attachment:abc-123") == "abc-123"


def test_attachment_ref_ignores_other_sources():
    assert attachment_ref("https://example.com/a.png") is None
    assert attachment_ref("data:image/png;base64,AAAA") is None
    assert attachment_ref("attachment:") is None


def test_scheme_constant_matches_the_syntax():
    assert ATTACHMENT_SCHEME == "attachment:"


def test_ids_are_collected_in_order_without_duplicates():
    content = "# T\n\n![a](attachment:one)\n\ntext\n\n![b](attachment:two)\n\n![c](attachment:one)\n"
    assert attachment_image_ids(content) == ["one", "two"]


def test_references_inside_code_fences_are_ignored():
    content = "```md\n![x](attachment:hidden)\n```\n\n![y](attachment:real)\n"
    assert attachment_image_ids(content) == ["real"]


def test_documents_without_attachments_yield_nothing():
    assert attachment_image_ids("![a](https://example.com/a.png)\n\nplain") == []
