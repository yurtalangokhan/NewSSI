"""Redaction of secrets and internal identifiers.

Two different jobs live here, and they are separated on purpose.

*Payload* redaction masks values under sensitive *field names*, so a dict bound
for a log, a trace, a checkpoint, or a model keeps its shape while losing the
fields that carry credentials or internal references. Which field names are
sensitive is a **service policy**, not a property of this module — the same
mechanism is used by services that redact different sets, and a mechanism that
hard-coded the union would leak one service's definition into another's.

*Text* redaction scrubs values that look like credentials wherever they appear
in a line of free text — a bearer token in a log message, a password in a URL.
This is the half that is safe to share, because it keys on the shape of the
secret rather than on where it sits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

#: Matches `scheme://user:password@host` and keeps only the host.
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][\w+.-]*://)(?P<user>[^/\s:@]+):(?P<pw>[^/\s@]+)@")

#: A labelled secret: `password=hunter2`, `api_key: sk-...`. The separator is
#: required. Without it, prose like "the token budget is 4096" would be redacted,
#: which is how a scrubber trains people to ignore its output.
_LABELLED = re.compile(
    r"(?i)\b(bearer|token|apikey|api_key|secret|password|passwd|pwd)\b"
    r"\s*[:=]\s*(?P<val>[^\s,;\"'}\]]+)"
)

#: `Bearer <credential>` with no separator, which is how the header is written.
_BEARER = re.compile(r"(?i)\bbearer\s+(?P<val>[A-Za-z0-9._~+/-]+=*)")

#: High-entropy strings that look like a credential with no label at all.
_OPAQUE_KEY = re.compile(r"\b(?:sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b")

MASKED = "***REDACTED***"


def redact_text(text: str) -> str:
    """Scrub credential-shaped substrings out of free text.

    Three passes, in order of confidence: URL credentials are unambiguous;
    a labelled secret is almost always real; an opaque key matching a known
    provider prefix is a strong hint. Anything else is left alone, because
    redacting aggressively makes logs unreadable and trains people to ignore them.
    """
    text = _URL_CREDENTIALS.sub(r"\g<scheme>\g<user>:***@", text)
    text = _LABELLED.sub(lambda m: f"{m.group(1)}={MASKED}", text)
    text = _BEARER.sub(f"Bearer {MASKED}", text)
    return _OPAQUE_KEY.sub(MASKED, text)


class Redactor:
    """Masks values under a service's own set of sensitive field names.

    Field matching is case-insensitive, and a field is redacted by exact name or
    by any of the configured prefixes — prefix matching is how per-instance
    header families (``x-binding-ref-<id>``) are covered without enumerating
    them.
    """

    __slots__ = ("_fields", "_prefixes", "_placeholder")

    def __init__(
        self,
        fields: Iterable[str] = (),
        *,
        prefixes: Iterable[str] = (),
        placeholder: str = MASKED,
    ) -> None:
        self._fields = frozenset(f.lower() for f in fields)
        self._prefixes = tuple(p.lower() for p in prefixes)
        self._placeholder = placeholder

    def is_sensitive(self, key: str) -> bool:
        """Whether a dict key under `key` should be masked."""
        lowered = key.lower()
        return lowered in self._fields or lowered.startswith(self._prefixes)

    def payload(self, value: Any) -> Any:
        """Return a copy of *value* with sensitive fields masked.

        Mappings keep their keys and lose their values; sequences keep their
        element type. Every other value is returned unchanged, so this is safe to
        apply to a structure it does not understand.
        """
        if isinstance(value, dict):
            return {
                k: (
                    self._placeholder
                    if isinstance(k, str) and self.is_sensitive(k)
                    else self.payload(v)
                )
                for k, v in value.items()
            }
        if isinstance(value, list | tuple):
            return type(value)(self.payload(v) for v in value)
        return value


__all__ = ["MASKED", "Redactor", "redact_text"]
