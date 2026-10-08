"""Spec: chat session titles come from a schema-constrained model call that
degrades in named, logged steps -- never from keyword frequency, never from
substring-matching a provider's apology, and never silently.

The stack this replaces failed in four ways that all reached users:

* A bag-of-words ranker emitted titles like "kubernetes docker deployment
  ingress" -- the four most frequent tokens, in frequency order.
* "No provider available" was detected by searching the response text for
  English phrases such as "no llm models are currently available". Reword the
  apology and it becomes a session title.
* The model's answer was free text scrubbed with regexes, so a model that
  wrapped its answer in quotes, prefixed "Title:", or added a sentence of
  explanation produced a title that was wrong in a different way each time.
* Every failure path was ``except Exception: return ""`` -- no log line, no
  way to tell an outage from a bad answer.

Language is not detected here and no language is named in code: the schema
makes the model declare the user's language (BCP-47) before it writes the
title, so Chinese, Arabic or Japanese input works through the same path as
English with no language-specific branch.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from infrastructure.llm.llm import FakeToolModel, UnavailableModel
from service.chat.chat_title_service import (
    DEFAULT_SESSION_NAME,
    ChatTitleService,
    GeneratedTitle,
    TitleResult,
    TitleSource,
    normalize_title,
    resolve_display_name,
    truncate_to_word_boundary,
)

TURKISH_QUESTION = "Docker container'ım başlarken sürekli exit 137 veriyor, neden olabilir?"


class _StructuredBinding:
    """Stands in for the runnable ``with_structured_output`` returns."""

    def __init__(self, owner: "_FakeModel") -> None:
        self._owner = owner

    def with_retry(self, **_kwargs: object) -> "_StructuredBinding":
        return self

    async def ainvoke(self, messages: list, config: object = None) -> dict:
        self._owner.structured_prompts.append(messages)
        if self._owner.structured_raises is not None:
            raise self._owner.structured_raises
        return self._owner.structured_envelope


class _FakeModel:
    """Chat model recording what it was asked and replaying canned answers."""

    def __init__(
        self,
        *,
        structured_envelope: dict | None = None,
        structured_raises: Exception | None = None,
        structured_supported: bool = True,
        free_text: str = "",
    ) -> None:
        self.structured_envelope = structured_envelope or {}
        self.structured_raises = structured_raises
        self.structured_supported = structured_supported
        self.free_text = free_text
        self.structured_prompts: list[list] = []
        self.free_text_prompts: list[list] = []
        self.structured_schema: type | None = None
        self.structured_kwargs: dict = {}

    def with_structured_output(self, schema: type, **kwargs: object) -> _StructuredBinding:
        if not self.structured_supported:
            raise NotImplementedError("this server does not support json_schema")
        self.structured_schema = schema
        self.structured_kwargs = dict(kwargs)
        return _StructuredBinding(self)

    async def ainvoke(self, messages: list, config: object = None) -> AIMessage:
        self.free_text_prompts.append(messages)
        return AIMessage(content=self.free_text)


def _service(model: object, **kwargs: object) -> ChatTitleService:
    return ChatTitleService(model_factory=lambda _name: model, **kwargs)


def _envelope(language: str, title: str) -> dict:
    return {
        "raw": AIMessage(content=""),
        "parsed": GeneratedTitle(language=language, title=title),
        "parsing_error": None,
    }


# --------------------------------------------------------------------------
# GeneratedTitle schema
# --------------------------------------------------------------------------


def test_schema_declares_language_before_title() -> None:
    """Field order is the mechanism, not decoration.

    Constrained decoders emit object keys in schema order, so putting
    ``language`` first makes the model commit to the user's language before
    it writes a single word of the title. Reverse the order and the title is
    already written by the time the language is named, which is exactly the
    "model picks a language per turn" behaviour this replaces.
    """
    assert list(GeneratedTitle.model_fields) == ["language", "title"]


def test_schema_strips_wrappers_a_model_adds_around_its_answer() -> None:
    assert GeneratedTitle(language="en", title='  "Docker exit code 137".  ').title == (
        "Docker exit code 137"
    )


def test_schema_keeps_a_colon_that_belongs_to_the_title() -> None:
    """There is no "strip a leading label" rule, on purpose.

    Telling `Başlık: X` (a label) from `Docker: exit 137` (a title with a
    colon in it) requires knowing what the word before the colon means, and
    every encoding of that is a word list per language. The prompt forbids
    label prefixes instead, so a colon that survives here is the user's topic,
    not a label -- and must not be eaten.
    """
    assert GeneratedTitle(language="en", title="Docker: exit code 137").title == (
        "Docker: exit code 137"
    )


def test_schema_keeps_only_the_first_line_of_a_chatty_answer() -> None:
    generated = GeneratedTitle(
        language="en",
        title="Docker memory limit\n\nLet me know if you want more detail!",
    )

    assert generated.title == "Docker memory limit"


def test_schema_rejects_an_empty_title() -> None:
    with pytest.raises(ValidationError):
        GeneratedTitle(language="en", title="   ")


def test_schema_rejects_a_whole_paragraph() -> None:
    with pytest.raises(ValidationError):
        GeneratedTitle(language="en", title=" ".join(["word"] * 30))


def test_schema_accepts_a_scriptless_language_without_counting_words() -> None:
    """Chinese writes a title with no spaces at all.

    A word-count rule based on whitespace reads this as one token and would
    reject it under any "at least N words" floor -- which is why the length
    rule is in characters and the token ceiling is generous.
    """
    assert GeneratedTitle(language="zh-Hans", title="Docker 容器内存不足问题").title == (
        "Docker 容器内存不足问题"
    )


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_output_title_is_returned_as_final() -> None:
    model = _FakeModel(structured_envelope=_envelope("tr", "Docker exit 137 hatası"))

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.title == "Docker exit 137 hatası"
    assert result.provisional is False
    assert result.reason is None


@pytest.mark.asyncio
async def test_structured_output_is_requested_as_json_schema_with_the_raw_envelope() -> None:
    """``include_raw`` is what makes a parse failure visible instead of an exception."""
    model = _FakeModel(structured_envelope=_envelope("en", "Docker exit code 137"))

    await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert model.structured_schema is GeneratedTitle
    assert model.structured_kwargs["method"] == "json_schema"
    assert model.structured_kwargs["include_raw"] is True


@pytest.mark.asyncio
async def test_the_assistant_reply_is_given_to_the_model_as_context() -> None:
    """A first message of "merhaba" carries no topic; the reply does."""
    model = _FakeModel(structured_envelope=_envelope("tr", "Selamlaşma ve tanışma"))

    await _service(model).generate(
        TitleSource(
            user_message="merhaba", assistant_message="Merhaba! Size nasıl yardımcı olabilirim?"
        )
    )

    prompt = "\n".join(str(message.content) for message in model.structured_prompts[0])
    assert "merhaba" in prompt
    assert "nasıl yardımcı olabilirim" in prompt


@pytest.mark.asyncio
async def test_the_prompt_names_no_language_of_its_own() -> None:
    """Whatever language the user wrote in must reach the model through the
    schema, not through a branch in this repo. Naming languages in the prompt
    is how the old code ended up supporting exactly two."""
    model = _FakeModel(structured_envelope=_envelope("zh-Hans", "Docker 内存不足"))

    await _service(model).generate(TitleSource(user_message="我的 Docker 容器一直退出 137"))

    prompt = "\n".join(str(message.content) for message in model.structured_prompts[0])
    assert "Turkish" not in prompt
    assert "English" not in prompt


@pytest.mark.asyncio
async def test_long_inputs_are_truncated_before_they_reach_the_model() -> None:
    model = _FakeModel(structured_envelope=_envelope("en", "Long input handling"))

    await _service(model).generate(
        TitleSource(user_message="u" * 5000, assistant_message="a" * 5000)
    )

    prompt = "\n".join(str(message.content) for message in model.structured_prompts[0])
    assert "u" * 5000 not in prompt
    assert "a" * 5000 not in prompt


# --------------------------------------------------------------------------
# Degradation ladder
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_provider_skips_the_model_entirely() -> None:
    """The placeholder must never be invoked: its "response" is an apology,
    and invoking it is exactly how that apology became a session title."""

    class _ExplodingPlaceholder(UnavailableModel):
        async def ainvoke(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("the unavailable placeholder must not be invoked")

    result = await _service(_ExplodingPlaceholder(responses=["apology"])).generate(
        TitleSource(user_message=TURKISH_QUESTION)
    )

    assert result.provisional is True
    assert result.reason == "no_model"
    assert "Docker" in result.title


@pytest.mark.asyncio
async def test_a_server_rejecting_json_schema_falls_back_to_free_text() -> None:
    model = _FakeModel(structured_supported=False, free_text="Docker exit code 137")

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.title == "Docker exit code 137"
    assert result.provisional is False
    assert model.free_text_prompts, "the free-text attempt should have run"


@pytest.mark.asyncio
async def test_a_schema_parse_failure_falls_back_to_free_text() -> None:
    model = _FakeModel(
        structured_envelope={
            "raw": AIMessage(content="{not json"),
            "parsed": None,
            "parsing_error": ValueError("invalid json"),
        },
        free_text="Container memory limit",
    )

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.title == "Container memory limit"
    assert result.provisional is False


@pytest.mark.asyncio
async def test_every_model_attempt_failing_yields_a_provisional_truncation() -> None:
    model = _FakeModel(structured_raises=RuntimeError("upstream 503"), free_text="")

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.provisional is True
    assert result.reason is not None
    assert result.title.startswith("Docker container'ım")


@pytest.mark.asyncio
async def test_a_hanging_provider_does_not_hang_the_request() -> None:
    class _Hanging(_FakeModel):
        async def ainvoke(self, messages: list, config: object = None) -> AIMessage:
            await asyncio.sleep(30)
            raise AssertionError("unreachable")

    model = _Hanging(structured_supported=False)

    result = await _service(model, timeout_seconds=0.05).generate(
        TitleSource(user_message=TURKISH_QUESTION)
    )

    assert result.provisional is True
    assert result.reason == "timeout"


@pytest.mark.asyncio
async def test_a_title_that_merely_echoes_the_question_is_rejected() -> None:
    """Copying the message back is not a summary, and it is what the weaker
    models do when the instruction to summarise does not land."""
    model = _FakeModel(
        structured_envelope=_envelope("tr", TURKISH_QUESTION[:60]),
        free_text="",
    )

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.provisional is True


@pytest.mark.asyncio
async def test_an_empty_exchange_keeps_the_default_name() -> None:
    model = _FakeModel(structured_envelope=_envelope("en", "Should not be used"))

    result = await _service(model).generate(
        TitleSource(user_message="   "), default_title="New Chat"
    )

    assert result == type(result)(title="New Chat", provisional=True, reason="empty_source")
    assert not model.structured_prompts


@pytest.mark.asyncio
async def test_a_deliberate_fake_model_is_still_used(caplog: pytest.LogCaptureFixture) -> None:
    """USE_FAKE_MODEL is a working stand-in, not an outage -- only the
    no-provider placeholder short-circuits."""
    model = FakeToolModel(responses=["Test session title"])

    result = await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert result.title == "Test session title"


@pytest.mark.asyncio
async def test_each_downgrade_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """The stack this replaces swallowed every failure with a bare except and
    no log line, so an outage and a bad answer looked identical in production."""
    model = _FakeModel(structured_raises=RuntimeError("upstream 503"), free_text="")

    with caplog.at_level("WARNING"):
        await _service(model).generate(TitleSource(user_message=TURKISH_QUESTION))

    assert "upstream 503" in caplog.text


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def test_truncation_does_not_split_a_word() -> None:
    assert truncate_to_word_boundary("Docker container restart loop diagnosis", 20) == (
        "Docker container…"
    )


def test_truncation_leaves_short_text_untouched() -> None:
    assert truncate_to_word_boundary("Docker hatası", 80) == "Docker hatası"


def test_truncation_of_scriptless_text_cuts_on_characters() -> None:
    """Chinese has no spaces to cut on; a word-boundary rule would return
    nothing at all and leave the session unnamed."""
    assert (
        truncate_to_word_boundary("我的容器一直重启这是为什么呢请帮我看看", 10)
        == "我的容器一直重启这…"
    )


def test_truncation_collapses_whitespace() -> None:
    assert truncate_to_word_boundary("Docker\n\n  hatası  ", 80) == "Docker hatası"


def test_normalize_title_is_idempotent() -> None:
    once = normalize_title('"Docker exit 137".')
    assert once == "Docker exit 137"
    assert normalize_title(once) == once


# --------------------------------------------------------------------------
# Display name resolution (shared by both listing surfaces)
# --------------------------------------------------------------------------


def test_a_stored_name_is_shown_as_is() -> None:
    resolved = resolve_display_name(stored_name="Ingress sertifikası", provisional_flag=False)

    assert resolved.title == "Ingress sertifikası"
    assert resolved.provisional is False


def test_a_stored_name_keeps_its_provisional_flag() -> None:
    resolved = resolve_display_name(stored_name="Kubernetes ingress…", provisional_flag=True)

    assert resolved.provisional is True


def test_a_never_named_session_gets_a_readable_stand_in() -> None:
    """Not a title -- a placeholder, and reported as one.

    Two endpoints used to build this inline as `content[:50]`, which lands
    mid-word, and both reported the result as if it were a real name.
    """
    resolved = resolve_display_name(
        stored_name=None,
        provisional_flag=False,
        first_user_message=(
            "Kubernetes ingress controller'ım sertifikayı yenilemiyor ve tarayıcı uyarı veriyor"
        ),
    )

    assert resolved.provisional is True
    assert resolved.title.endswith("…")
    assert "yenilemiyo…" not in resolved.title


def test_a_never_named_session_with_no_messages_falls_back_to_the_default() -> None:
    resolved = resolve_display_name(
        stored_name=None, provisional_flag=False, default_title="New Chat"
    )

    assert resolved == TitleResult("New Chat", provisional=True, reason="never_named")


def test_the_stored_placeholder_still_counts_as_never_named() -> None:
    """`New Chat` is a sentinel, not a name.

    ChatThreadService writes it into metadata for a fresh thread and treats it
    as absent everywhere else (`metadata.get("name") in (None, "", "New Chat")`).
    Reading it as a real title here would strand every session created that
    way with the placeholder.
    """
    resolved = resolve_display_name(
        stored_name=DEFAULT_SESSION_NAME,
        provisional_flag=False,
        first_user_message="Redis bağlantısı neden sürekli kopuyor acaba",
    )

    assert resolved.provisional is True
    assert resolved.title.startswith("Redis")


@pytest.mark.asyncio
async def test_an_explicit_llm_is_used_instead_of_the_model_factory() -> None:
    def _factory(name):
        raise AssertionError("the factory must not be consulted when an llm is given")

    llm = _FakeModel(structured_envelope=_envelope("tr", "Selamlaşma"))

    result = await ChatTitleService(model_factory=_factory).generate(
        TitleSource(user_message="merhaba"), model_name="gemini-3.8-flash", llm=llm
    )

    assert result.title == "Selamlaşma"
    assert result.provisional is False
