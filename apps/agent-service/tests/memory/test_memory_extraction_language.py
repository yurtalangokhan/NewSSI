"""Spec: the language a fact is stored in is decided by the model, declared in
the schema, and persisted -- never guessed by a marker list in this repo.

What this replaces and why:

The extraction prompt used to be pure English with no rule about the output
language, so the model decided per turn. Measured against the deployed models,
one user's facts came back partly English and partly Turkish ("The user likes
detective novels." next to "Kullanıcı sabahları erken kalkmayı sevmez."), and
Turkish first-person pronouns were read as English names ("Ben's birth year is
2004"). That is not cosmetic: recall scores a Turkish query against stored
facts with a Turkish-aware lexical pass, which cannot match an English fact at
all, so an English-stored fact is unreachable from a Turkish question.

The first fix detected the language in Python (`detect_response_language`) and
named it in the prompt with a worked example in that language. It worked for
the two languages the marker list knew. For every other language it returned
"same as input", the prompt named nothing, and the facts fell back to exactly
the bare rule this file had already recorded as insufficient -- so a Chinese or
Arabic user hit the original bug, silently.

The fix here moves both jobs into the schema:

* `language` is declared before `facts`. Constrained decoders emit keys in
  schema order, so the model commits to the user's language before it writes a
  single fact -- for any language, with no branch per language in this repo.
* `subject` sits between them: the exact third-person wording the facts must
  use to refer to the user, written in the language just declared. A worked
  example in the user's language cannot live in the prompt -- the prompt is
  built before anyone knows what language the user wrote in -- so the model
  writes that anchor itself, and it is in context while the facts are
  generated.

Both shapes were measured against llama3.1:8b, the deployed model:

  * asking for a whole example sentence gave `"Benim adı Burak'tır."` and
    first-person facts. Asking for the subject alone gave `"Kullanıcı"` and
    correct third-person facts, repeatably.
  * the English shape example in the prompt is load-bearing. Removing it
    produced `subject = "Ben"` and first-person facts again.
  * Chinese came back malformed under every variant tried. That is the
    model's own limit, not the prompt's: `language` is detected correctly
    ("zh-Hans") while the generated text is not usable Chinese.

The declared tag is stored with the fact, so a language mismatch becomes
measurable instead of silently unreachable.
"""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import memory.long_term as lt


class _BoundStructuredModel:
    def __init__(self, parent: "_PromptCapturingModel") -> None:
        self._parent = parent

    async def ainvoke(self, messages, config=None):
        self._parent.last_prompt = messages[0].content
        return self._parent.result


class _PromptCapturingModel:
    """Fake chat model that records the extraction prompt it was handed."""

    def __init__(self, result: lt.ExtractedFacts | None = None) -> None:
        self.last_prompt: str | None = None
        self.result = (
            result
            if result is not None
            else lt.ExtractedFacts(language="en", subject="The user", facts=[])
        )

    def with_structured_output(self, schema):
        return _BoundStructuredModel(self)


async def _noop_save(user_id, facts, **kwargs) -> None:
    """Stand in for the real persistence path, which would do HTTP I/O."""


class _WarningRecorder:
    """Collects `memory.long_term`'s warnings without depending on caplog.

    `core.observability.logger.get_logger` leaves a logger with
    `propagate = False` unless the root logger already had handlers when it
    was first called, so `memory.long_term`'s records never reach caplog's
    root handler. Watching the module's own logger object is independent of
    which module happened to be imported first.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def __call__(self, message, *args, **kwargs) -> None:
        self.messages.append(str(message) % args if args else str(message))

    @property
    def text(self) -> str:
        return "\n".join(self.messages).lower()


async def _drain_background() -> None:
    if lt._BACKGROUND_TASKS:
        await asyncio.wait_for(
            asyncio.gather(*list(lt._BACKGROUND_TASKS), return_exceptions=True), timeout=2.0
        )


async def _run_extraction(messages, result=None) -> str:
    model = _PromptCapturingModel(result)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt, "save_memories", _noop_save)
        await lt.extract_and_save_memories("user-1", messages, model)
        await _drain_background()
    assert model.last_prompt is not None
    return model.last_prompt


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_the_model_declares_the_language_before_it_writes_any_fact() -> None:
    """Field order is the mechanism, not presentation.

    Reverse it and every fact is already written by the time the language is
    named, which is the "model picks a language per turn" behaviour this
    replaces.
    """
    assert list(lt.ExtractedFacts.model_fields) == ["language", "subject", "facts"]


def test_no_field_is_optional() -> None:
    """Measured, not assumed: optional fields make the model answer `{}`.

    The first version of this schema defaulted every field so a thin answer
    would cost one field instead of the turn. Run against llama3.1:8b it cost
    everything -- with no field required, the model emitted a bare `{}` on
    every call and extraction produced nothing at all. The pre-existing
    `facts: list[str] = Field(default_factory=list)` had the same effect, so
    extraction was silently yielding zero facts on that model before this
    change too.

    Making the fields required flipped it to a full answer on the first try.
    A validation error is recoverable -- `_extract_and_save_memories_impl`
    catches it and the turn is retried on the next message; an empty object
    parses cleanly and looks like "this conversation had no facts".
    """
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        lt.ExtractedFacts()


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def test_the_prompt_dictates_no_output_language() -> None:
    """The risk is pinning the facts to a language, not mentioning one.

    The version this replaces built the prompt around
    `_LANGUAGE_EXAMPLES[detected]` and emitted "Write EVERY fact in Turkish"
    with a Turkish worked example -- which is why it supported exactly two
    languages and silently constrained nothing for the rest.

    The prompt here names one language, once, to say what the shape example is
    written in ("In English this is \"The user\""). That is measurably
    load-bearing: removing the example made llama3.1:8b answer a Turkish
    conversation with `subject = "Ben"` and first-person facts. It says
    nothing about which language the facts must be in -- the model decides
    that and declares it in `language`.
    """
    prompt = lt.MEMORY_EXTRACTION_SYSTEM_PROMPT

    # No language is offered as a target for the facts.
    for language in ("Turkish", "Chinese", "Japanese", "Arabic", "Kullanıcı"):
        assert language not in prompt

    # And nothing instructs the model to write the facts in a named language.
    assert "Write EVERY fact in" not in prompt
    assert "facts in English" not in prompt


def test_the_prompt_is_a_constant_not_a_builder() -> None:
    """Nothing can pass a detected language in any more.

    A `build_extraction_system_prompt()` that takes no argument and returns a
    constant would just be the old seam with the language removed -- keeping
    it invites the next change to thread a language back through it.
    """
    assert not hasattr(lt, "build_extraction_system_prompt")


def test_the_prompt_demands_third_person_without_naming_a_language() -> None:
    """The formulation rule used to live inside the Turkish worked example.

    Dropping the per-language examples means the rule has to be stated in a
    way that holds for any language, or the models go back to answering in the
    user's own voice ("Adım Ali Burak") instead of stating a fact about them.
    """
    prompt = lt.MEMORY_EXTRACTION_SYSTEM_PROMPT.lower()

    assert "third person" in prompt
    assert "own voice" in prompt


def test_the_prompt_warns_that_pronouns_are_not_names() -> None:
    """Generalised from the Turkish-only "ben is not a name" note."""
    prompt = lt.MEMORY_EXTRACTION_SYSTEM_PROMPT.lower()

    assert "pronoun" in prompt
    assert "never the user's name" in prompt


def test_the_prompt_carries_a_shape_example() -> None:
    """The example is load-bearing, measured against llama3.1:8b.

    The same prompt with the example removed produced `subject = "Ben"` for a
    Turkish conversation -- the first-person pronoun -- and every fact came
    back in the user's own voice. With the example it produced
    `subject = "Kullanıcı"` and correct third-person facts, repeatably.

    It is an example of the *shape*, written in English because the prompt is
    English. It names no language the facts have to be in, which is what
    separates it from the per-language worked examples it replaces.
    """
    prompt = lt.MEMORY_EXTRACTION_SYSTEM_PROMPT

    assert "The user" in prompt
    assert "My name is" in prompt


def test_the_prompt_states_the_field_order_it_expects() -> None:
    prompt = lt.MEMORY_EXTRACTION_SYSTEM_PROMPT

    assert prompt.index("`language`") < prompt.index("`subject`") < prompt.index("`facts`")


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_declared_subject_never_reaches_storage_as_a_fact() -> None:
    """`subject` is the wording facts must use, not a fact of its own."""
    saved: list[list[str]] = []

    async def _capture(user_id, facts, **kwargs):
        saved.append(list(facts))

    result = lt.ExtractedFacts(
        language="tr",
        subject="Kullanıcı",
        facts=["Kullanıcı", "Kullanıcı Kayseri'de yaşıyor."],
    )
    model = _PromptCapturingModel(result)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt, "save_memories", _capture)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="Ben Kayseri'de yaşıyorum.")], model
        )
        await _drain_background()

    assert saved == [["Kullanıcı Kayseri'de yaşıyor."]]


@pytest.mark.asyncio
async def test_the_declared_language_is_passed_on_for_storage() -> None:
    """Storing it is what makes a wrong-language fact measurable.

    Until now a fact written in the wrong language was simply never recalled,
    and nothing anywhere recorded which language it was in.
    """
    captured: dict = {}

    async def _capture(user_id, facts, **kwargs):
        captured.update(kwargs)

    result = lt.ExtractedFacts(
        language="zh-Hans",
        subject="用户",
        facts=["用户住在开塞利。"],
    )
    model = _PromptCapturingModel(result)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt, "save_memories", _capture)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="我住在开塞利")], model
        )
        await _drain_background()

    assert captured["language"] == "zh-Hans"


@pytest.mark.asyncio
async def test_a_fact_that_diverges_from_the_models_own_exemplar_is_logged() -> None:
    """The exemplar is the yardstick, so the check needs no language knowledge.

    "Adım Ali Burak." opens nothing like "Kullanıcının adı Ayşe." -- that is
    the first-person regression, visible without knowing a word of Turkish.
    """
    result = lt.ExtractedFacts(
        language="tr",
        subject="Kullanıcı",
        facts=["Adım Ali Burak."],
    )
    model = _PromptCapturingModel(result)

    warnings = _WarningRecorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt.logger, "warning", warnings)
        # Without this the real save path runs, reaches out to user-service
        # over HTTP and hangs -- which made the "no warning" cases below pass
        # for the wrong reason.
        mp.setattr(lt, "save_memories", _noop_save)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="Adım Ali Burak")], model
        )
        await _drain_background()

    assert "diverges" in warnings.text


@pytest.mark.asyncio
async def test_a_fact_matching_the_exemplar_is_not_flagged() -> None:
    result = lt.ExtractedFacts(
        language="tr",
        subject="Kullanıcı",
        facts=["Kullanıcı Kayseri'de yaşıyor."],
    )
    model = _PromptCapturingModel(result)

    warnings = _WarningRecorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt.logger, "warning", warnings)
        # Without this the real save path runs, reaches out to user-service
        # over HTTP and hangs -- which made the "no warning" cases below pass
        # for the wrong reason.
        mp.setattr(lt, "save_memories", _noop_save)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="Kayseri'de yaşıyorum")], model
        )
        await _drain_background()

    assert "diverges" not in warnings.text


@pytest.mark.asyncio
async def test_no_declared_subject_means_no_divergence_check() -> None:
    """A model that left `subject` blank must not make every fact look wrong."""
    result = lt.ExtractedFacts(language="tr", subject="", facts=["Adım Ali Burak."])
    model = _PromptCapturingModel(result)

    warnings = _WarningRecorder()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt.logger, "warning", warnings)
        # Without this the real save path runs, reaches out to user-service
        # over HTTP and hangs -- which made the "no warning" cases below pass
        # for the wrong reason.
        mp.setattr(lt, "save_memories", _noop_save)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="Adım Ali Burak")], model
        )
        await _drain_background()

    assert "diverges" not in warnings.text


@pytest.mark.asyncio
async def test_short_facts_are_still_filtered_out() -> None:
    """Pre-existing guard; the new fields must not have displaced it."""
    saved: list[list[str]] = []

    async def _capture(user_id, facts, **kwargs):
        saved.append(list(facts))

    result = lt.ExtractedFacts(
        language="en", subject="The user", facts=["ok", "The user is 21."]
    )
    model = _PromptCapturingModel(result)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lt, "save_memories", _capture)
        await lt.extract_and_save_memories(
            "user-1", [HumanMessage(content="I am 21")], model
        )
        await _drain_background()

    assert saved == [["The user is 21."]]


@pytest.mark.asyncio
async def test_only_the_users_own_words_reach_the_extractor() -> None:
    """Unchanged trust boundary: an AIMessage can be the echo of an earlier
    prompt injection, so it is not allowed to decide anything that gets
    written to memory -- including the language."""
    prompt = await _run_extraction(
        [
            HumanMessage(content="I was born in 2004 and I live in Kayseri."),
            AIMessage(content="Kayseri güzel bir şehirdir, doğum gününüz ne zaman?"),
        ]
    )

    assert "güzel bir şehirdir" not in prompt
    assert "I was born in 2004" in prompt


# ---------------------------------------------------------------------------
# The marker list is gone
# ---------------------------------------------------------------------------


def test_the_hardcoded_language_detector_is_gone() -> None:
    """No shim: the marker list must not survive anywhere."""
    assert not hasattr(lt, "detect_response_language")
    assert not hasattr(lt, "_LANGUAGE_EXAMPLES")

    with pytest.raises(ModuleNotFoundError):
        __import__("core.utils.language")


def test_core_utils_no_longer_exports_it() -> None:
    import core.utils as utils

    assert "detect_response_language" not in utils.__all__


# ---------------------------------------------------------------------------
# The divergence check itself
# ---------------------------------------------------------------------------


def test_divergence_ignores_inflection_the_language_adds() -> None:
    """Turkish suffixes the subject ("Kullanıcı" -> "Kullanıcı'nın").

    The check is a prefix test for exactly this reason: llama3.1:8b returns
    `subject = "Kullanıcı"` and then writes "Kullanıcı'nın adı ...", which an
    equality test would flag on every well-formed Turkish fact.
    """
    assert not lt._diverges_from_subject("Kullanıcı", "Kullanıcı'nın adı Ayşe.")


def test_divergence_catches_a_first_person_answer() -> None:
    """The regression measured on llama3.1:8b without the shape example."""
    assert lt._diverges_from_subject("Kullanıcı", "Adım Ali Burak.")


def test_divergence_works_on_a_script_without_spaces() -> None:
    """Chinese packs the subject into two characters and uses no spaces.

    A word-boundary rule would compare whole sentences here and flag
    everything; the character-prefix rule separates 用户… from 我… correctly.
    """
    assert not lt._diverges_from_subject("用户", "用户住在开塞利。")
    assert lt._diverges_from_subject("用户", "我住在开塞利。")


def test_divergence_is_case_insensitive() -> None:
    assert not lt._diverges_from_subject("The user", "the user lives in Izmir.")


def test_divergence_ignores_surrounding_whitespace() -> None:
    assert not lt._diverges_from_subject("  The user  ", "The  user  is 21.")


def test_a_missing_subject_never_flags_anything() -> None:
    """A model that skipped the field must not make every fact look wrong."""
    assert not lt._diverges_from_subject("", "Adım Ali Burak.")
    assert not lt._diverges_from_subject("Kullanıcı", "")
