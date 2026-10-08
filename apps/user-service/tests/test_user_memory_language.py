"""Spec: a memory fact carries the language it was written in, end to end.

agent-service's extractor now has the model declare the user's language
(BCP-47) as part of its structured answer instead of guessing it from a
hardcoded Turkish/English marker list. That tag has to survive the trip into
this service's canonical store, because the failure it guards against is
otherwise invisible: a fact written in the wrong language is simply never
recalled -- recall scores a query against stored facts with a language-aware
lexical pass, which cannot match across languages -- and nothing anywhere
recorded which language a fact was in.

The column is nullable on purpose. Rows written before this existed, and facts
a user typed in by hand, have no declared language, and "unknown" is not the
same as any particular language. Defaulting them to one would record a guess
as if it were an observation.
"""

import uuid

import pytest

from src.core.database.models import UserMemoryModel
from src.service.user_memory_service import UserMemoryService


class _Row:
    def __init__(self, content: str, language: str | None) -> None:
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.content = content
        self.source = "auto_extracted"
        self.language = language
        self.time_created = None
        self.time_updated = None


class _RecordingRepo:
    """Captures what the service hands the repository."""

    def __init__(self, created: list[_Row] | None = None) -> None:
        self.bulk_create_items: list[tuple] = []
        self.created = created if created is not None else []

    async def bulk_create(self, user_id, items):
        self.bulk_create_items = list(items)
        return self.created

    async def delete_oldest_excess(self, user_id, keep):
        return 0


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> UserMemoryService:
    svc = UserMemoryService()
    # The rag-service sync is fire-and-forget background I/O; this spec is
    # about what reaches Postgres.
    monkeypatch.setattr(svc, "_sync_upsert", lambda *a, **k: None)
    return svc


# ---------------------------------------------------------------------------
# Model and schema
# ---------------------------------------------------------------------------


def test_the_model_has_a_nullable_language_column() -> None:
    column = UserMemoryModel.__table__.columns["language"]

    assert column.nullable is True
    assert column.type.length == 35, "RFC 5646 tags fit in 35 characters"


# ---------------------------------------------------------------------------
# Service -> repository
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_declared_language_reaches_the_repository(service) -> None:
    repo = _RecordingRepo()
    service.repo = repo

    await service.add_facts(uuid.uuid4(), ["Kullanıcı Kayseri'de yaşıyor."], language="tr")

    assert repo.bulk_create_items == [("Kullanıcı Kayseri'de yaşıyor.", "auto_extracted", "tr")]


@pytest.mark.asyncio
async def test_no_declared_language_is_stored_as_null_not_as_a_guess(service) -> None:
    repo = _RecordingRepo()
    service.repo = repo

    await service.add_facts(uuid.uuid4(), ["The user is 21."])

    assert repo.bulk_create_items == [("The user is 21.", "auto_extracted", None)]


@pytest.mark.asyncio
async def test_an_empty_language_string_is_normalised_to_null(service) -> None:
    """agent-service omits the field when undeclared, but a "" must not become
    a distinct third state in the column."""
    repo = _RecordingRepo()
    service.repo = repo

    await service.add_facts(uuid.uuid4(), ["The user is 21."], language="   ")

    assert repo.bulk_create_items == [("The user is 21.", "auto_extracted", None)]


@pytest.mark.asyncio
async def test_every_fact_in_one_batch_carries_the_same_declared_language(service) -> None:
    """The extractor declares one language per conversation, not per fact."""
    repo = _RecordingRepo()
    service.repo = repo

    await service.add_facts(
        uuid.uuid4(), ["用户住在开塞利。", "用户是工程师。"], language="zh-Hans"
    )

    assert [item[2] for item in repo.bulk_create_items] == ["zh-Hans", "zh-Hans"]


@pytest.mark.asyncio
async def test_deduplication_still_applies_with_a_language(service) -> None:
    """Pre-existing behaviour; the extra field must not have displaced it."""
    repo = _RecordingRepo()
    service.repo = repo

    await service.add_facts(
        uuid.uuid4(), ["Kullanıcı 21 yaşında.", "kullanıcı 21 yaşında."], language="tr"
    )

    assert len(repo.bulk_create_items) == 1


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_the_serialized_memory_exposes_its_language(service) -> None:
    payload = service._memory_to_dict(_Row("Kullanıcı Kayseri'de yaşıyor.", "tr"))

    assert payload["language"] == "tr"


def test_a_language_less_row_serializes_as_none(service) -> None:
    payload = service._memory_to_dict(_Row("The user is 21.", None))

    assert payload["language"] is None


def test_the_existing_payload_fields_are_untouched(service) -> None:
    """`_to_dict()` serialization is a documented invariant of this service;
    this change is additive only."""
    payload = service._memory_to_dict(_Row("The user is 21.", None))

    assert set(payload) == {
        "id",
        "user_id",
        "content",
        "source",
        "language",
        "time_created",
        "time_updated",
    }


# ---------------------------------------------------------------------------
# Route -> controller
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_controller_forwards_the_language_to_the_service() -> None:
    from src.controller.user_memory_controller import UserMemoryController

    captured: dict = {}

    class _Service:
        async def add_facts(self, user_id, contents, source="auto_extracted", language=None):
            captured.update(
                {"user_id": user_id, "contents": contents, "source": source, "language": language}
            )
            return []

    controller = UserMemoryController()
    controller.service = _Service()
    user_id = uuid.uuid4()

    await controller.add_facts(user_id, ["用户住在开塞利。"], language="zh-Hans")

    assert captured["language"] == "zh-Hans"


@pytest.mark.asyncio
async def test_a_bulk_body_without_a_language_reaches_the_controller_as_none() -> None:
    """agent-service omits the key when the model declared nothing, so the
    route must read an absent key as "unknown", not fail or invent one."""
    from src.controller.user_memory_controller import UserMemoryController

    captured: dict = {}

    class _Service:
        async def add_facts(self, user_id, contents, source="auto_extracted", language=None):
            captured["language"] = language
            return []

    controller = UserMemoryController()
    controller.service = _Service()

    body = {"contents": ["The user is 21."], "source": "auto_extracted"}
    await controller.add_facts(uuid.uuid4(), body["contents"], language=body.get("language"))

    assert captured["language"] is None
