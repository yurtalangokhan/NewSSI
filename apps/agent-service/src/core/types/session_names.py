"""Chat session naming sentinels shared across layers."""

from __future__ import annotations

#: The name a session carries until it has a real one. It is a sentinel, not
#: a title: ChatThreadService writes it into a fresh thread's metadata and then
#: treats it as absent (`metadata.get("name") in (None, "", "New Chat")`), so
#: anything reading a stored name has to do the same or the placeholder sticks.
DEFAULT_SESSION_NAME = "New Chat"
