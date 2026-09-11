"""Tests for icon allowlist completeness against all registered templates and opal exports.

Spec: .tmp/flow-canvas-design.md sections 4.4, 7.1, 7.2, 7.3.
Brief: .tmp/flow-canvas-task-34-brief.md
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.flows.registry import get_registry
from domain.flows.templates.icons import ICON_ALLOWLIST


def test_every_registered_template_has_icon_in_allowlist():
    """34.1 — Every template across all categories uses an icon present in ICON_ALLOWLIST."""
    registry = get_registry()
    grouped = registry.list_grouped(include_deprecated=True)
    all_templates = [t for group in grouped.values() for t in group]

    assert len(all_templates) >= 30, f"Expected at least 30 templates, got {len(all_templates)}"

    for template in all_templates:
        assert template.icon in ICON_ALLOWLIST, (
            f"Template '{template.type}' (category '{template.category}') has icon '{template.icon}' "
            "which is missing from ICON_ALLOWLIST"
        )


def test_allowlist_icons_exist_in_opal_exports():
    """34.2 — Every icon in ICON_ALLOWLIST is physically exported by @opal/icons index.ts."""
    index_ts = (
        Path(__file__).resolve().parents[4] / "web" / "lib" / "opal" / "src" / "icons" / "index.ts"
    )
    if not index_ts.exists():
        index_ts = Path("/home/alipekisik/Projects/agenticai/apps/web/lib/opal/src/icons/index.ts")

    if not index_ts.exists():
        pytest.skip("apps/web not present on disk in this test runner environment")

    content = index_ts.read_text(encoding="utf-8")
    for icon_name in ICON_ALLOWLIST:
        expected_export = f"export {{ default as {icon_name} }}"
        assert expected_export in content, (
            f"Icon '{icon_name}' from ICON_ALLOWLIST is not exported in {index_ts}"
        )
