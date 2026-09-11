"""Pure title-generation helpers for chat sessions.

Extracted from ``ChatController`` to reduce the controller's LOC and make the
title logic independently testable.  All functions here are stateless.
"""

from __future__ import annotations

import re


def is_invalid_generated_title(title: str) -> bool:
    """Return True if *title* looks like an LLM error message rather than a real title."""
    text = (title or "").strip().lower()
    if not text:
        return True

    invalid_markers = [
        "no llm models are currently available",
        "please ensure your llm provider",
        "check the admin panel",
        "no llm providers are configured",
        "model '",
        "not found",
    ]
    return any(marker in text for marker in invalid_markers)


def normalize_title(raw_title: str) -> str:
    """Clean and truncate a raw LLM-generated title."""
    title = (raw_title or "").strip()
    if not title:
        return ""

    # Keep only the first line and trim common wrappers like "Baslik:".
    title = title.splitlines()[0].strip()
    title = re.sub(r"^(baslik|başlık|title)\s*[:\-]\s*", "", title, flags=re.IGNORECASE)
    title = title.strip("\"'`''[](){}.,;:!? ")
    title = re.sub(r"\s+", " ", title).strip()
    return title[:80]


def detect_response_language(text: str) -> str:
    """Heuristic language detection for title generation prompting."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return "same as input"

    # Quick Turkish signal via unique characters.
    if re.search(r"[çğıöşü]", lowered):
        return "Turkish"

    tokens = re.findall(r"[a-zA-Z]+", lowered)
    if not tokens:
        return "same as input"

    tr_markers = {
        "ve",
        "ile",
        "icin",
        "için",
        "bir",
        "bu",
        "gibi",
        "daha",
        "olarak",
        "ancak",
        "cunku",
        "çünkü",
        "sonra",
        "kadar",
    }
    en_markers = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "into",
        "about",
        "before",
        "after",
    }

    tr_score = sum(1 for t in tokens if t in tr_markers)
    en_score = sum(1 for t in tokens if t in en_markers)

    if tr_score > en_score:
        return "Turkish"
    if en_score > tr_score:
        return "English"
    return "same as input"


def is_trivial_prefix_title(title: str, source_text: str) -> bool:
    """Reject titles that are just the opening words of the response."""
    title_words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", title.lower())
    source_words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", source_text.lower())
    if not title_words or len(source_words) < len(title_words):
        return False
    return source_words[: len(title_words)] == title_words


def heuristic_title_from_ai_response(ai_response: str) -> str:
    """Build a short summary-like title from assistant response text without using an LLM."""
    cleaned = re.sub(r"\s+", " ", (ai_response or "")).strip()
    if not cleaned:
        return ""

    words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", cleaned)
    stopwords = {
        "ve",
        "veya",
        "ile",
        "için",
        "icin",
        "bu",
        "bir",
        "the",
        "and",
        "for",
        "that",
        "from",
        "your",
        "you",
        "olarak",
        "ancak",
        "çünkü",
        "sonuç",
        "buna",
        "göre",
        "daha",
        "gibi",
        "olur",
        "olacak",
        "yapmak",
        "yapabilir",
        "adım",
        "1",
        "2",
        "3",
    }

    # Score keywords by frequency and reward words that appear beyond the opening phrase.
    frequencies: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for idx, word in enumerate(words):
        lw = word.lower()
        if len(lw) <= 2 or lw in stopwords:
            continue
        frequencies[lw] = frequencies.get(lw, 0) + 1
        first_seen.setdefault(lw, idx)

    if not frequencies:
        return ""

    ranked = sorted(
        frequencies.keys(),
        key=lambda w: (
            frequencies[w],
            -first_seen[w],
        ),
        reverse=True,
    )

    selected = ranked[:4]
    title = " ".join(selected).strip().capitalize()
    if is_invalid_generated_title(title):
        return ""
    if is_trivial_prefix_title(title, ai_response):
        return ""
    return title[:80]
