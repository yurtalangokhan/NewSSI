"""`ask_user` argümanlarının doğrulanması ve normalleştirilmesi.

Doğrulama neden burada, pydantic'te değil: pydantic hatası aracı hiç
çalıştırmadan bir exception'a dönüşürdü. Bizim istediğimiz, modelin hatayı
okuyup düzeltilmiş bir çağrı yapabilmesi — yani hata da bir araç sonucu
olmalı. Bu yüzden araç imzası gevşek (``list[dict]``) ve doğrulama burada.
"""

from typing import Any

MAX_QUESTIONS = 4
MIN_OPTIONS = 2
MAX_OPTIONS = 4


class InvalidQuestions(Exception):
    """Mesajı doğrudan modele gider; okunabilir ve düzeltilebilir olmalı."""


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _validate_options(raw: Any, header: str) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise InvalidQuestions(f"Question '{header}': `options` must be a list.")
    if not MIN_OPTIONS <= len(raw) <= MAX_OPTIONS:
        raise InvalidQuestions(
            f"Question '{header}': give between {MIN_OPTIONS} and {MAX_OPTIONS} options "
            f"(got {len(raw)}). One option is not a choice; more than {MAX_OPTIONS} is a list."
        )

    options: list[dict[str, str]] = []
    for option in raw:
        if not isinstance(option, dict):
            raise InvalidQuestions(
                f"Question '{header}': each option must be an object with a `label`."
            )
        label = _text(option.get("label"))
        if not label:
            raise InvalidQuestions(f"Question '{header}': every option needs a non-empty `label`.")
        options.append({"label": label, "description": _text(option.get("description"))})
    return options


def validate_questions(raw: Any) -> list[dict[str, Any]]:
    """Doğrulanmış, normalleştirilmiş soru listesi. Hata → ``InvalidQuestions``."""
    if not isinstance(raw, list):
        raise InvalidQuestions("`questions` must be a list of question objects.")
    if not raw:
        raise InvalidQuestions("`questions` must hold at least one question.")
    if len(raw) > MAX_QUESTIONS:
        raise InvalidQuestions(
            f"Ask at most {MAX_QUESTIONS} questions per call (got {len(raw)}). "
            "Ask the ones that matter most; the rest can wait."
        )

    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise InvalidQuestions("Each question must be an object.")

        header = _text(item.get("header"))
        if not header:
            raise InvalidQuestions("Every question needs a short non-empty `header` (1-3 words).")
        if header in seen:
            raise InvalidQuestions(
                f"Duplicate `header`: '{header}'. Headers are the answer keys, so they must "
                "be unique within one call."
            )
        seen.add(header)

        question = _text(item.get("question"))
        if not question:
            raise InvalidQuestions(f"Question '{header}': `question` text may not be empty.")

        multi = item.get("multiSelect", item.get("multi_select", False))
        questions.append(
            {
                "question": question,
                "header": header,
                "options": _validate_options(item.get("options"), header),
                "multiSelect": bool(multi),
            }
        )
    return questions
