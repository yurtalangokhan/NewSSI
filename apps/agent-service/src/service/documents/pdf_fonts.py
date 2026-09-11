"""PDF font registration and family resolution.

DOCX can reference any font by name and let Word resolve it; ReportLab needs
the TTF on disk and registered up front. A requested family (Calibri,
Georgia, Consolas...) is mapped to whichever DejaVu bucket is closest, and a
missing bold/italic/bold-italic variant falls back to the regular file
rather than to base-14 Helvetica — Helvetica can't render Turkish glyphs, so
silently substituting it would break the one thing DejaVu was registered
for.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class FontFamily:
    name: str
    regular: str
    bold: str
    italic: str
    bold_italic: str


_HELVETICA_FALLBACK = FontFamily(
    name="Helvetica",
    regular="Helvetica",
    bold="Helvetica-Bold",
    italic="Helvetica-Oblique",
    bold_italic="Helvetica-BoldOblique",
)

_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "sans": {
        "regular": ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",),
        "bold": ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",),
        "italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",),
        "bold_italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",),
    },
    "serif": {
        "regular": ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",),
        "bold": ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",),
        "italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",),
        "bold_italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",),
    },
    "mono": {
        "regular": ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",),
        "bold": ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",),
        "italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",),
        "bold_italic": ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",),
    },
}

_FAMILY_ALIASES: dict[str, str] = {
    "calibri": "sans",
    "calibri light": "sans",
    "arial": "sans",
    "helvetica": "sans",
    "verdana": "sans",
    "segoe ui": "sans",
    "georgia": "serif",
    "times new roman": "serif",
    "times": "serif",
    "cambria": "serif",
    "garamond": "serif",
    "consolas": "mono",
    "courier new": "mono",
    "courier": "mono",
}

_registered_families: dict[str, FontFamily] = {}
_registration_attempted = False


def _existing_path(candidates: tuple[str, ...], fallback: str) -> str:
    return next((p for p in candidates if os.path.exists(p)), fallback)


def _register_all() -> None:
    global _registration_attempted
    if _registration_attempted:
        return
    _registration_attempted = True

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for bucket, paths in _CANDIDATES.items():
        regular_path = _existing_path(paths["regular"], "")
        if not regular_path:
            logger.warning("No TTF found for PDF font bucket '%s'; falling back to base-14", bucket)
            continue

        bold_path = _existing_path(paths["bold"], regular_path)
        italic_path = _existing_path(paths["italic"], regular_path)
        bold_italic_path = _existing_path(paths["bold_italic"], bold_path)

        base = f"Doc{bucket.capitalize()}"
        bold_name, italic_name, bold_italic_name = (
            f"{base}-Bold",
            f"{base}-Italic",
            f"{base}-BoldItalic",
        )

        pdfmetrics.registerFont(TTFont(base, regular_path))
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        pdfmetrics.registerFont(TTFont(italic_name, italic_path))
        pdfmetrics.registerFont(TTFont(bold_italic_name, bold_italic_path))
        pdfmetrics.registerFontFamily(
            base, normal=base, bold=bold_name, italic=italic_name, boldItalic=bold_italic_name
        )
        _registered_families[bucket] = FontFamily(
            base, base, bold_name, italic_name, bold_italic_name
        )


def resolve_font_family(requested: str | None) -> FontFamily:
    """Map a requested family name to a registered ReportLab font family.

    Falls back to the sans bucket for unrecognized names, and to base-14
    Helvetica only if no DejaVu TTF could be registered at all (in which
    case non-Latin1 text will not render — the same limitation the original
    single-font PDF renderer had).
    """
    _register_all()
    bucket = _FAMILY_ALIASES.get((requested or "").strip().lower(), "sans")
    return (
        _registered_families.get(bucket) or _registered_families.get("sans") or _HELVETICA_FALLBACK
    )
