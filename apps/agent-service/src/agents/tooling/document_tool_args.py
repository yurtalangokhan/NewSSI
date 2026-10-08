"""Repair of document tool arguments that models commonly get wrong.

Smaller and local models misplace the body, the style options or the edit
list. Rejecting those calls costs the user a full regeneration, so these
helpers recover the intent where it is unambiguous and leave anything else to
normal schema validation.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Keys smaller models reach for instead of `content` when passing the body.
_CONTENT_ALIASES = (
    "content",
    "text",
    "body",
    "markdown",
    "md",
    "document",
    "document_content",
    "content_markdown",
)

# Some models emit the body wrapped in pseudo-XML inside another argument,
# e.g. {"filename": "...", "title": "<content># Heading\n...</content>"}. The
# tags also turn up unpaired, with the provider's parser having eaten the other
# half, so opening and closing markers are matched independently.
_WRAPPER_TAGS = "content|document|body|markdown|tool_call"
_CONTENT_TAG_RE = re.compile(rf"</?\s*({_WRAPPER_TAGS})\s*>", re.IGNORECASE)

# An explicit `content` is only unwrapped when the wrapper is the whole value
# (or a lone marker sits at its very start or end); a tag anywhere else is the
# author's own text, e.g. an HTML tutorial.
_WHOLE_WRAP_RE = re.compile(rf"^\s*<\s*({_WRAPPER_TAGS})\s*>(.*)<\s*/\s*\1\s*>\s*$", re.DOTALL | re.IGNORECASE)
_LEADING_MARKER_RE = re.compile(rf"^\s*<\s*({_WRAPPER_TAGS})\s*>", re.IGNORECASE)
_TRAILING_MARKER_RE = re.compile(rf"</\s*({_WRAPPER_TAGS})\s*>\s*$", re.IGNORECASE)

# Code fences are copied through verbatim: markup inside them is content.
_FENCE_RE = re.compile(r"^(?P<fence>`{3,}|~{3,}).*?(?:^(?P=fence)[ \t]*$|\Z)", re.DOTALL | re.MULTILINE)

# Arguments that are never the document body.
_NON_BODY_KEYS = frozenset({"filename", "format", "title", "name", "path"})

# A stray argument this long, spanning several lines, is the body rather than a
# stray label — short values are left alone so a description is never promoted.
_BODY_MIN_LENGTH = 200


def strip_content_markup(text: str) -> str:
    """Remove pseudo-XML content/tool-call markers a model left in the body.

    Fenced code blocks are left as written.
    """
    parts: list[str] = []
    cursor = 0
    for fence in _FENCE_RE.finditer(text):
        parts.append(_CONTENT_TAG_RE.sub("", text[cursor : fence.start()]))
        parts.append(fence.group(0))
        cursor = fence.end()
    parts.append(_CONTENT_TAG_RE.sub("", text[cursor:]))
    return "".join(parts).strip()


def unwrap_content_markup(text: str) -> str:
    """Unwrap a body that is wholly wrapped in a marker pair, or that carries a
    lone unpaired marker at its very start or end; anything else is returned
    unchanged (no trimming, nothing inside the text is touched).
    """
    whole = _WHOLE_WRAP_RE.match(text)
    if whole:
        return whole.group(2)
    for pattern, closing in ((_LEADING_MARKER_RE, "</"), (_TRAILING_MARKER_RE, "<")):
        marker = pattern.search(text)
        if marker is None:
            continue
        tag = marker.group(1)
        # A marker whose partner appears elsewhere is real text, not an orphan.
        partner = re.search(rf"<\s*/\s*{tag}\s*>" if closing == "</" else rf"<\s*{tag}\s*>", text, re.IGNORECASE)
        if partner is None:
            return text[: marker.start()] + text[marker.end() :]
    return text


# Top-level DocumentOptions section names — see service.documents.options.
_OPTIONS_TOP_LEVEL_KEYS = frozenset(
    {
        "theme",
        "font",
        "colors",
        "page",
        "cover",
        "toc",
        "numbering",
        "header",
        "footer",
        "front_matter",
        "tables",
        "requirement_ids",
        "watermark",
        "pdf",
    }
)


def _gather_stray_options(args: dict[str, Any]) -> dict[str, Any]:
    """Fold style keys a model placed at the top level (e.g. `theme=...`
    alongside `filename`/`format`/`content`) into `options`, instead of
    leaving them as unknown arguments the schema would reject.
    """
    stray = {key: args[key] for key in _OPTIONS_TOP_LEVEL_KEYS if key in args}
    if not stray:
        return args

    repaired = {key: value for key, value in args.items() if key not in stray}
    existing = args.get("options")
    if existing is None:
        repaired["options"] = stray
    elif isinstance(existing, dict):
        repaired["options"] = {**stray, **existing}
    else:
        repaired["options"] = existing
    return repaired


def recover_document_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Repair a `create_document` call that put the body somewhere else, or
    style keys somewhere other than `options`.

    Local models pass the document under `text`/`body`, or inline it as
    `<content>…</content>` — often with only one half of the tag pair surviving
    the provider's own parser. Rejecting those costs the user a full
    regeneration of a long document, so recover the body where the intent is
    clear and leave anything ambiguous to normal validation. Style keys
    dropped at the top level (`theme=...`) are gathered into `options`.

    Only ever *adds* `content` (and cleans markup out of it); the document body
    is never invented from a short unrelated argument.
    """
    if not isinstance(args, dict):
        return args

    return _recover_content(_gather_stray_options(args))


def _recover_content(args: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(args)

    # For format="json", a model naturally reaches for a dict/list rather
    # than a pre-serialized string; `content` is typed str, so pydantic would
    # reject the call outright. Serialize it here instead of forcing the
    # model to notice and redo the call.
    existing = repaired.get("content")
    if isinstance(existing, (dict, list)):
        repaired["content"] = json.dumps(existing, ensure_ascii=False)
        return repaired

    if isinstance(existing, str) and existing.strip():
        unwrapped = unwrap_content_markup(existing)
        if unwrapped.strip() and unwrapped != existing:
            repaired["content"] = unwrapped
            return repaired
        return args

    for alias in _CONTENT_ALIASES:
        value = repaired.get(alias)
        if isinstance(value, (dict, list)):
            repaired["content"] = json.dumps(value, ensure_ascii=False)
            if alias != "content":
                repaired.pop(alias, None)
            return repaired
        if isinstance(value, str) and value.strip():
            repaired["content"] = strip_content_markup(value)
            if alias != "content":
                repaired.pop(alias, None)
            return repaired

    # A full <content>…</content> pair is unambiguous wherever it appears.
    for key, value in list(repaired.items()):
        if not isinstance(value, str):
            continue
        match = re.search(r"<\s*(content|document|body)\s*>(.*?)</\s*\1\s*>", value, re.DOTALL | re.IGNORECASE)
        if not match or not match.group(2).strip():
            continue
        repaired["content"] = match.group(2).strip()
        remainder = strip_content_markup(value.replace(match.group(0), ""))
        if remainder:
            repaired[key] = remainder
        else:
            repaired.pop(key, None)
        return repaired

    # Otherwise take a stray argument that carries a lone marker, or one long
    # enough that it can only be the document itself.
    for key, value in list(repaired.items()):
        if key in _NON_BODY_KEYS or not isinstance(value, str):
            continue
        looks_like_body = _CONTENT_TAG_RE.search(value) or (len(value) >= _BODY_MIN_LENGTH and "\n" in value)
        if not looks_like_body:
            continue
        cleaned = strip_content_markup(value)
        if not cleaned:
            continue
        repaired["content"] = cleaned
        repaired.pop(key, None)
        return repaired

    return args


# Names models use for the two halves of an edit instead of old_str / new_str.
_EDIT_KEY_ALIASES = {"old": "old_str", "old_text": "old_str", "new": "new_str", "new_text": "new_str"}


def _normalize_edit(edit: Any) -> Any:
    if not isinstance(edit, dict):
        return edit
    normalized = dict(edit)
    for alias, canonical in _EDIT_KEY_ALIASES.items():
        if alias in normalized and canonical not in normalized:
            normalized[canonical] = normalized.pop(alias)
    return normalized


def recover_edit_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Repair an `edit_document` call whose `edits` list is mis-shaped.

    Models send `edits` as a JSON string, as one bare edit object, with
    `old`/`new` (or `old_text`/`new_text`) keys, or drop a lone
    `old_str`/`new_str` pair at the top level. Each is normalized to the
    schema's list of `{old_str, new_str, replace_all}`; a string that is not
    valid JSON is left for validation to reject with a clear message.
    """
    if not isinstance(args, dict):
        return args

    repaired = _gather_stray_options(args)
    options = repaired.get("options")
    if isinstance(options, str):
        try:
            decoded = json.loads(options)
        except ValueError:
            decoded = None
        if isinstance(decoded, dict):
            repaired = {**repaired, "options": decoded}
    edits = repaired.get("edits")
    if edits is None and any(key in repaired for key in ("old_str", "old", "old_text")):
        pair_keys = ("old_str", "new_str", "replace_all", *_EDIT_KEY_ALIASES)
        edits = {key: repaired[key] for key in pair_keys if key in repaired}
        repaired = {key: value for key, value in repaired.items() if key not in pair_keys}
    if isinstance(edits, str):
        try:
            edits = json.loads(edits)
        except ValueError:
            return repaired
    if isinstance(edits, dict):
        edits = [edits]
    if isinstance(edits, list):
        repaired = {**repaired, "edits": [_normalize_edit(edit) for edit in edits]}
    return repaired
