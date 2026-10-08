from infrastructure.db.models import AuthoredDocumentModel, AuthoredDocumentRevisionModel


def test_revision_uniqueness_and_lookup_indexes() -> None:
    table = AuthoredDocumentRevisionModel.__table__
    unique = {tuple(c.name for c in cons.columns) for cons in table.constraints if cons.__class__.__name__ == "UniqueConstraint"}
    assert ("document_id", "revision_no") in unique
    assert {"ix_authored_document_revisions_rendered_file_id"} <= {i.name for i in table.indexes}


def test_document_scoping_indexes() -> None:
    names = {i.name for i in AuthoredDocumentModel.__table__.indexes}
    assert {"ix_authored_documents_user_id", "ix_authored_documents_thread_id"} <= names


def test_deleting_a_thread_deletes_its_documents() -> None:
    """A deleted chat must not leave orphaned drafts no route can list."""
    (fk,) = AuthoredDocumentModel.__table__.c.thread_id.foreign_keys
    assert fk.ondelete == "CASCADE"
