"""Named visual themes and the theme/override merge used by the renderers.

`DocumentOptions.font`/`.colors` leave their family/color fields unset
(`None`) by default specifically so this module can tell "not specified,
use the theme" apart from "explicitly overridden" — see
`resolve_effective_style`.
"""

from __future__ import annotations

from dataclasses import dataclass

from service.documents.options import DocumentOptions


@dataclass(frozen=True)
class ThemeDefinition:
    name: str
    body_font: str
    heading_font: str
    mono_font: str
    heading_color: str
    accent_color: str
    text_color: str
    table_header_bg: str
    table_header_text: str
    table_zebra_bg: str
    code_bg: str
    link_color: str


_THEMES: dict[str, ThemeDefinition] = {
    "default": ThemeDefinition(
        name="default",
        body_font="Calibri",
        heading_font="Calibri Light",
        mono_font="Consolas",
        heading_color="#1F4E79",
        accent_color="#2E74B5",
        text_color="#000000",
        table_header_bg="#1F4E79",
        table_header_text="#FFFFFF",
        table_zebra_bg="#F2F2F2",
        code_bg="#F5F5F5",
        link_color="#0563C1",
    ),
    "corporate_blue": ThemeDefinition(
        name="corporate_blue",
        body_font="Calibri",
        heading_font="Calibri Light",
        mono_font="Consolas",
        heading_color="#0B3D91",
        accent_color="#1560BD",
        text_color="#0A0A0A",
        table_header_bg="#0B3D91",
        table_header_text="#FFFFFF",
        table_zebra_bg="#E8EEF9",
        code_bg="#EEF2FA",
        link_color="#1560BD",
    ),
    "minimal_gray": ThemeDefinition(
        name="minimal_gray",
        body_font="Calibri",
        heading_font="Calibri",
        mono_font="Consolas",
        heading_color="#333333",
        accent_color="#666666",
        text_color="#222222",
        table_header_bg="#E0E0E0",
        table_header_text="#000000",
        table_zebra_bg="#F5F5F5",
        code_bg="#F0F0F0",
        link_color="#4A4A4A",
    ),
    "academic": ThemeDefinition(
        name="academic",
        body_font="Georgia",
        heading_font="Georgia",
        mono_font="Courier New",
        heading_color="#7A1F2B",
        accent_color="#7A1F2B",
        text_color="#1A1A1A",
        table_header_bg="#7A1F2B",
        table_header_text="#FFFFFF",
        table_zebra_bg="#F4E9EA",
        code_bg="#F2F2F2",
        link_color="#7A1F2B",
    ),
    "dark_accent": ThemeDefinition(
        name="dark_accent",
        body_font="Calibri",
        heading_font="Calibri Light",
        mono_font="Consolas",
        heading_color="#212121",
        accent_color="#E67E22",
        text_color="#1A1A1A",
        table_header_bg="#212121",
        table_header_text="#FFFFFF",
        table_zebra_bg="#EDEDED",
        code_bg="#E8E8E8",
        link_color="#E67E22",
    ),
}


def resolve_theme(name: str) -> ThemeDefinition:
    return _THEMES.get(name, _THEMES["default"])


@dataclass(frozen=True)
class EffectiveStyle:
    body_font: str
    heading_font: str
    mono_font: str
    font_size: int
    line_spacing: float
    space_after: int
    heading_color: str
    accent_color: str
    text_color: str
    table_header_bg: str
    table_header_text: str
    table_zebra_bg: str
    code_bg: str
    link_color: str


def resolve_effective_style(options: DocumentOptions) -> EffectiveStyle:
    """Merge the resolved theme with any explicit font/color overrides."""
    theme = resolve_theme(options.theme)
    font = options.font
    colors = options.colors
    return EffectiveStyle(
        body_font=font.body or theme.body_font,
        heading_font=font.heading or theme.heading_font,
        mono_font=font.mono or theme.mono_font,
        font_size=font.size,
        line_spacing=font.line_spacing,
        space_after=font.space_after,
        heading_color=colors.heading or theme.heading_color,
        accent_color=colors.accent or theme.accent_color,
        text_color=colors.text or theme.text_color,
        table_header_bg=colors.table_header_bg or theme.table_header_bg,
        table_header_text=colors.table_header_text or theme.table_header_text,
        table_zebra_bg=colors.table_zebra_bg or theme.table_zebra_bg,
        code_bg=colors.code_bg or theme.code_bg,
        link_color=colors.link or theme.link_color,
    )
