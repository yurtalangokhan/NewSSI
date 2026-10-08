"""The web client pre-checks Mermaid sources against a mirrored size cap.

The server (``env.MERMAID_MAX_SOURCE_CHARS``) stays authoritative; the client
constant only avoids a doomed render. They must ship with the same default, or
the panel accepts diagrams the server rejects (or the reverse).
"""

from __future__ import annotations

import re
from pathlib import Path

from config_manager import env

WEB_SOURCE = Path(__file__).parents[4] / "apps/web/src/components/mermaid/mermaidSource.ts"


def test_web_mermaid_cap_matches_the_server_default(monkeypatch) -> None:
    monkeypatch.delenv("MERMAID_MAX_SOURCE_CHARS", raising=False)
    match = re.search(r"MERMAID_MAX_SOURCE_CHARS\s*=\s*([\d_]+)", WEB_SOURCE.read_text())
    assert match, "web constant MERMAID_MAX_SOURCE_CHARS not found"
    assert int(match.group(1).replace("_", "")) == env.MERMAID_MAX_SOURCE_CHARS
