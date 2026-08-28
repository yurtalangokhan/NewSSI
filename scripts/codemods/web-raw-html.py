#!/usr/bin/env python3
"""Codemod: migrate raw <p>/<h1>-<h6> primitives to <Text as="...">.

Mechanical, behavior-preserving part of Tier 2 (web raw-HTML) from the
codebase-simplification spec. Only touches files that contain NO
<button>/<input>/<textarea>/<img> primitives (those need per-component review
against the refresh-components API) AND that do not already define or import a
local `Text` component under a conflicting name.

Replacement rules (DOM tag + className preserved via the `as` prop):
  <p ...>   -> <Text as="p" ...>      (TextElement supports "p")
  <h1 ...>  -> <Text as="h1" ...>     (TextElement extended to h1-h6)
  ...
  <h6 ...>  -> <Text as="h6" ...>

The refresh-components `Text` component (src/refresh-components/texts/Text.tsx)
now accepts h1-h6 in its `as` prop (it renders via React.createElement, so the
DOM tag is preserved exactly). No font props are injected, so existing
className-based styling is preserved.

Usage:
  python3 scripts/codemods/web-raw-html.py [--dry-run] [file ...]
If no files given, reads the list from /tmp/web-pure-text-files.txt.
Files that are skipped (foreign/local Text) are reported and excluded.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REFRESH_TEXT_IMPORT_RE = re.compile(
    r'^\s*import\s+.*\bText\b.*from\s+["\']@/refresh-components/texts/Text["\']',
    re.MULTILINE,
)
# Any import that brings `Text` in from a path that is NOT the refresh Text.
FOREIGN_TEXT_IMPORT_RE = re.compile(
    r'^\s*import\s+.*\bText\b.*from\s+["\']((?!@/refresh-components/texts/Text).)*["\']',
    re.MULTILINE,
)
# Local declaration of `Text` (function/const/class/interface/type).
LOCAL_TEXT_DECL_RE = re.compile(
    r'^\s*(export\s+)?(default\s+)?(function|const|let|var|class|interface|type)\s+Text\b',
    re.MULTILINE,
)
# A JSX usage of <Text ...> already present (means Text is in scope somehow).
EXISTING_TEXT_JSX_RE = re.compile(r"<\s*Text\b")

OPEN_RE = re.compile(r"<\s*(p|h[1-6])\b([^>]*)>")
CLOSE_RE = re.compile(r"<\s*/(p|h[1-6])\s*>")


def classify(src: str) -> str:
    """Return 'ok', 'foreign', or 'local' for Text-import safety."""
    if LOCAL_TEXT_DECL_RE.search(src):
        return "local"
    if FOREIGN_TEXT_IMPORT_RE.search(src):
        return "foreign"
    return "ok"


def transform(src: str) -> str:
    def open_sub(m: re.Match) -> str:
        tag, rest = m.group(1), m.group(2).strip()
        return f'<Text as="{tag}" {rest}>' if rest else f'<Text as="{tag}">'

    out = OPEN_RE.sub(open_sub, src)
    out = CLOSE_RE.sub(lambda m: "</Text>", out)

    if "<Text" in out and not REFRESH_TEXT_IMPORT_RE.search(out):
        out = _add_text_import(out)
    return out


def _add_text_import(src: str) -> str:
    import_stmt = 'import Text from "@/refresh-components/texts/Text";'
    lines = src.split("\n")
    last_import_end = -1
    for i, line in enumerate(lines):
        if re.search(r'\bfrom\s+["\'].*["\']\s*;?\s*$', line):
            last_import_end = i
    if last_import_end >= 0:
        lines.insert(last_import_end + 1, import_stmt)
    else:
        lines.insert(0, import_stmt)
    return "\n".join(lines)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    files = [a for a in sys.argv[1:] if a != "--dry-run"] or (
        Path("/tmp/web-pure-text-files.txt").read_text().split()
        if Path("/tmp/web-pure-text-files.txt").exists()
        else []
    )

    changed = 0
    skipped = []
    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"SKIP (missing): {f}")
            continue
        before = p.read_text()
        kind = classify(before)
        if kind != "ok":
            skipped.append((f, kind))
            continue
        after = transform(before)
        if after != before:
            changed += 1
            if dry_run:
                print(f"WOULD CHANGE: {f}")
            else:
                p.write_text(after)
                print(f"CHANGED: {f}")
    for f, kind in skipped:
        print(f"SKIP ({kind} Text): {f}")
    print(f"\n{changed} file(s) {'would be ' if dry_run else ''}changed; {len(skipped)} skipped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
