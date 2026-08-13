"""PDF rendering from the parsed block tree.

Every block becomes ReportLab flowables with inline formatting expressed
through paragraph markup (Group C), plus the full page scaffolding and
theme application (Group A/B/F1): page size/orientation/margins,
header/footer with deferred `{pages}` resolution (see
`pdf_canvas.NumberedCanvas`), watermark, cover page, a real table of
contents built via `multiBuild`, a PDF navigation outline (bookmarks per
heading), document metadata, and theme fonts/colors resolved through
`pdf_fonts` (Word font names have no meaning to ReportLab — they're mapped
to whichever registered TTF bucket is closest).
"""

from __future__ import annotations

import io
import logging
from typing import Any

from service.documents import header_footer
from service.documents.blocks import (
    Block,
    BulletListBlock,
    CodeBlock,
    FootnoteDefBlock,
    HeadingBlock,
    HorizontalRuleBlock,
    ImageBlock,
    InlineSpan,
    ListItem,
    OrderedListBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
)
from service.documents.image_loading import load_image_bytes
from service.documents.numbering import prepare_blocks
from service.documents.options import (
    CoverOptions,
    DocumentOptions,
    HeaderFooterOptions,
    TableStyleOptions,
    WatermarkOptions,
)
from service.documents.pdf_canvas import NumberedCanvas
from service.documents.pdf_fonts import resolve_font_family
from service.documents.pdf_header_footer import needs_deferred_page_count, resolve_segment
from service.documents.themes import EffectiveStyle, resolve_effective_style

logger = logging.getLogger(__name__)

_IMAGE_TARGET_WIDTH_PT = 420
_LIST_INDENT_STEP_PT = 14
_LIST_BASE_INDENT_PT = 14
_COVER_LOGO_WIDTH_PT = 115


def _escape_pdf_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_styles(
    style: EffectiveStyle, table_options: TableStyleOptions | None = None
) -> dict[str, Any]:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    table_options = table_options or TableStyleOptions()
    body_family = resolve_font_family(style.body_font)
    heading_family = resolve_font_family(style.heading_font)
    mono_family = resolve_font_family(style.mono_font)

    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "DocBody",
        parent=base["Normal"],
        fontName=body_family.regular,
        fontSize=style.font_size,
        leading=style.font_size * style.line_spacing,
        textColor=HexColor(style.text_color),
        spaceAfter=style.space_after,
    )
    title = ParagraphStyle(
        "DocTitle",
        parent=base["Title"],
        fontName=heading_family.bold,
        fontSize=22,
        leading=26,
        textColor=HexColor(style.heading_color),
    )
    headings = {
        level: ParagraphStyle(
            f"DocHeading{level}",
            parent=base["Heading1"],
            fontName=heading_family.bold,
            fontSize=max(18 - level * 2, 12),
            leading=max(22 - level * 2, 16),
            textColor=HexColor(style.heading_color),
        )
        for level in range(1, 7)
    }
    code = ParagraphStyle(
        "DocCode",
        parent=base["Code"],
        fontName=mono_family.regular,
        fontSize=9,
        leading=12,
        backColor=HexColor(style.code_bg),
    )
    quote = ParagraphStyle(
        "DocQuote",
        parent=body,
        leftIndent=24,
        textColor=HexColor(style.text_color),
        spaceBefore=4,
        spaceAfter=4,
    )
    caption = ParagraphStyle(
        "DocCaption", parent=body, fontSize=9, leading=12, textColor=HexColor(style.text_color)
    )
    return {
        "title": title,
        "body": body,
        "headings": headings,
        "code": code,
        "quote": quote,
        "caption": caption,
        "body_font_name": body_family.regular,
        "body_font_bold_name": body_family.bold,
        "mono_font": mono_family.regular,
        "link_color": style.link_color,
        "table_header_bg": style.table_header_bg,
        "table_header_text": style.table_header_text,
        "table_zebra_bg": style.table_zebra_bg,
        "table_style": table_options.style,
        "table_header_bold": table_options.header_bold,
    }


# ---------------------------------------------------------------------------
# Inline span → ReportLab paragraph markup
# ---------------------------------------------------------------------------


def _spans_to_markup(spans: list[InlineSpan], styles: dict[str, Any] | None = None) -> str:
    mono_font = (styles or {}).get("mono_font", "Courier")
    link_color = (styles or {}).get("link_color", "#0563C1")

    parts: list[str] = []
    for span in spans:
        if span.footnote_id:
            parts.append(f"<super>[{_escape_pdf_xml(span.footnote_id)}]</super>")
            continue
        text = _escape_pdf_xml(span.text)
        if span.code:
            text = f'<font face="{mono_font}">{text}</font>'
        if span.bold:
            text = f"<b>{text}</b>"
        if span.italic:
            text = f"<i>{text}</i>"
        if span.link:
            text = f'<link href="{_escape_pdf_xml(span.link)}" color="{link_color}">{text}</link>'
        parts.append(text)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def _pdf_list_flowables(
    items: list[ListItem], is_ordered: bool, styles: dict[str, Any] | None = None
) -> list[Any]:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    styles = styles or _pdf_styles(resolve_effective_style(DocumentOptions()))
    body_style = styles["body"]
    flowables: list[Any] = []
    counters: dict[int, int] = {}

    for item in items:
        for level in [lvl for lvl in counters if lvl > item.level]:
            del counters[level]
        counters[item.level] = counters.get(item.level, 0) + 1

        if is_ordered:
            marker = f"{counters[item.level]}."
        elif item.checked is not None:
            marker = "☑" if item.checked else "☐"
        else:
            marker = "•" if item.level == 0 else "◦"

        indent = _LIST_BASE_INDENT_PT + item.level * _LIST_INDENT_STEP_PT
        style = ParagraphStyle(
            f"list-{is_ordered}-{item.level}-{id(item)}", parent=body_style, leftIndent=indent
        )
        flowables.append(Paragraph(f"{marker} {_spans_to_markup(item.spans, styles)}", style))

    return flowables


# ---------------------------------------------------------------------------
# Block dispatch
# ---------------------------------------------------------------------------


def _pdf_table_flowable(block: TableBlock, styles: dict[str, Any]) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import Paragraph, Table, TableStyle

    align_map = {"left": "LEFT", "center": "CENTER", "right": "RIGHT"}
    data = [
        [Paragraph(_spans_to_markup(cell.spans, styles), styles["body"]) for cell in row]
        for row in (block.header, *block.rows)
    ]
    table = Table(data)
    style_commands = [
        ("FONTNAME", (0, 0), (-1, -1), styles["body_font_name"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor(styles["table_header_text"])),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(styles["table_header_bg"])),
    ]
    if styles["table_header_bold"]:
        style_commands.append(("FONTNAME", (0, 0), (-1, 0), styles["body_font_bold_name"]))
    if styles["table_style"] != "minimal":
        style_commands.append(("GRID", (0, 0), (-1, -1), 0.5, colors.grey))
    if styles["table_style"] == "zebra":
        for row_index in range(2, len(data), 2):
            style_commands.append(
                ("BACKGROUND", (0, row_index), (-1, row_index), HexColor(styles["table_zebra_bg"]))
            )
    if block.alignments:
        for col, alignment in enumerate(block.alignments):
            style_commands.append(("ALIGN", (col, 0), (col, -1), align_map.get(alignment, "LEFT")))
    table.setStyle(TableStyle(style_commands))
    return table


def _pdf_flowables_for_block(block: Block, styles: dict[str, Any]) -> list[Any]:
    from reportlab.platypus import HRFlowable, PageBreak, Paragraph, Spacer

    if isinstance(block, HeadingBlock):
        style = styles["headings"].get(block.level, styles["headings"][6])
        return [Paragraph(_spans_to_markup(block.spans, styles), style), Spacer(1, 6)]
    if isinstance(block, ParagraphBlock):
        return [Paragraph(_spans_to_markup(block.spans, styles), styles["body"]), Spacer(1, 6)]
    if isinstance(block, BulletListBlock):
        return [*_pdf_list_flowables(block.items, is_ordered=False, styles=styles), Spacer(1, 6)]
    if isinstance(block, OrderedListBlock):
        return [*_pdf_list_flowables(block.items, is_ordered=True, styles=styles), Spacer(1, 6)]
    if isinstance(block, CodeBlock):
        from reportlab.platypus import Preformatted

        return [Preformatted(block.text, styles["code"]), Spacer(1, 6)]
    if isinstance(block, QuoteBlock):
        prefix = f"<b>{block.callout_type}:</b> " if block.callout_type else ""
        return [
            Paragraph(f"{prefix}{_spans_to_markup(block.spans, styles)}", styles["quote"]),
            Spacer(1, 6),
        ]
    if isinstance(block, TableBlock):
        flowables: list[Any] = [_pdf_table_flowable(block, styles)]
        if block.caption:
            flowables.append(Paragraph(_escape_pdf_xml(block.caption), styles["caption"]))
        flowables.append(Spacer(1, 6))
        return flowables
    if isinstance(block, ImageBlock):
        return _pdf_image_flowables(block, styles)
    if isinstance(block, HorizontalRuleBlock):
        return [HRFlowable(width="100%", color="#999999", thickness=0.75), Spacer(1, 6)]
    if isinstance(block, PageBreakBlock):
        return [PageBreak()]
    if isinstance(block, FootnoteDefBlock):
        markup = f"<b>[{_escape_pdf_xml(block.id)}]</b> {_spans_to_markup(block.spans, styles)}"
        return [Paragraph(markup, styles["caption"]), Spacer(1, 4)]
    return []


def _pdf_image_flowables(block: ImageBlock, styles: dict[str, Any]) -> list[Any]:
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, Spacer

    data = load_image_bytes(block.src)
    if data is None:
        return []
    try:
        reader = ImageReader(io.BytesIO(data))
        original_width, original_height = reader.getSize()
        ratio = _IMAGE_TARGET_WIDTH_PT / original_width
        image = Image(
            io.BytesIO(data), width=_IMAGE_TARGET_WIDTH_PT, height=original_height * ratio
        )
    except Exception as exc:
        logger.warning("Could not decode image %s for PDF output: %s", block.src, exc)
        return []

    flowables: list[Any] = [image]
    if block.caption:
        flowables.append(Paragraph(_escape_pdf_xml(block.caption), styles["caption"]))
    flowables.append(Spacer(1, 6))
    return flowables


# ---------------------------------------------------------------------------
# Cover page
# ---------------------------------------------------------------------------


def _pdf_cover_flowables(
    cover: CoverOptions, title: str | None, styles: dict[str, Any]
) -> list[Any]:
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Image, PageBreak, Paragraph, Spacer

    flowables: list[Any] = []

    if cover.logo:
        data = load_image_bytes(cover.logo)
        if data is not None:
            from reportlab.lib.utils import ImageReader

            reader = ImageReader(io.BytesIO(data))
            original_width, original_height = reader.getSize()
            ratio = _COVER_LOGO_WIDTH_PT / original_width
            image = Image(
                io.BytesIO(data), width=_COVER_LOGO_WIDTH_PT, height=original_height * ratio
            )
            image.hAlign = "CENTER"
            flowables.append(image)
            flowables.append(Spacer(1, 12))

    if title:
        centered_title = ParagraphStyle("CoverTitle", parent=styles["title"], alignment=TA_CENTER)
        flowables.append(Paragraph(_escape_pdf_xml(title), centered_title))
        flowables.append(Spacer(1, 8))

    if cover.subtitle:
        subtitle_style = ParagraphStyle(
            "CoverSubtitle", parent=styles["body"], alignment=TA_CENTER, fontSize=14
        )
        flowables.append(Paragraph(f"<i>{_escape_pdf_xml(cover.subtitle)}</i>", subtitle_style))

    flowables.append(Spacer(1, 48))

    meta_style = ParagraphStyle("CoverMeta", parent=styles["body"], alignment=TA_CENTER)
    for value in (
        cover.project,
        f"v{cover.version}" if cover.version else "",
        cover.date,
        cover.author,
        cover.organization,
    ):
        if value:
            flowables.append(Paragraph(_escape_pdf_xml(value), meta_style))

    if cover.classification:
        flowables.append(Spacer(1, 12))
        flowables.append(Paragraph(f"<b>{_escape_pdf_xml(cover.classification)}</b>", meta_style))

    flowables.append(PageBreak())
    return flowables


# ---------------------------------------------------------------------------
# Page furniture — header/footer/watermark, drawn per page via onPage
# ---------------------------------------------------------------------------


def _resolve_page_size(page: Any) -> tuple[float, float]:
    from reportlab.lib.pagesizes import A4, LETTER, landscape

    base = A4 if page.size == "A4" else LETTER
    return landscape(base) if page.orientation == "landscape" else base


def _draw_hf_segment(
    canvas_obj: Any,
    template: str,
    x: float,
    align: str,
    y: float,
    page_num: int,
    substitutions: dict[str, str],
    font_name: str,
    font_size: float,
    color_hex: str,
) -> None:
    from reportlab.lib.colors import HexColor

    if not template:
        return
    if needs_deferred_page_count(template):
        resolved = resolve_segment(template, page_num, substitutions)
        canvas_obj.add_deferred_draw(resolved, x, y, align, font_name, font_size, color_hex)
        return

    text = resolve_segment(template, page_num, substitutions)
    canvas_obj.setFont(font_name, font_size)
    canvas_obj.setFillColor(HexColor(color_hex))
    draw = {
        "left": canvas_obj.drawString,
        "center": canvas_obj.drawCentredString,
        "right": canvas_obj.drawRightString,
    }[align]
    draw(x, y, text)


def _draw_header_footer_line(
    canvas_obj: Any,
    hf: HeaderFooterOptions,
    y: float,
    content_left: float,
    content_center: float,
    content_right: float,
    page_num: int,
    substitutions: dict[str, str],
    font_name: str,
    accent_color: str,
    text_color: str,
    rule_offset: float,
) -> None:
    for template, x, align in (
        (hf.left, content_left, "left"),
        (hf.center, content_center, "center"),
        (hf.right, content_right, "right"),
    ):
        _draw_hf_segment(
            canvas_obj, template, x, align, y, page_num, substitutions, font_name, 9, text_color
        )
    if hf.rule:
        from reportlab.lib.colors import HexColor

        canvas_obj.setStrokeColor(HexColor(accent_color))
        canvas_obj.line(content_left, y + rule_offset, content_right, y + rule_offset)


def _draw_watermark(
    canvas_obj: Any, page_size: tuple[float, float], watermark: WatermarkOptions
) -> None:
    from reportlab.lib.colors import HexColor

    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica-Bold", 60)
    canvas_obj.setFillColor(HexColor(watermark.color))
    canvas_obj.setFillAlpha(0.25)
    canvas_obj.translate(page_size[0] / 2, page_size[1] / 2)
    canvas_obj.rotate(45)
    canvas_obj.drawCentredString(0, 0, watermark.text)
    canvas_obj.restoreState()


def _draw_page_furniture(
    canvas_obj: Any,
    options: DocumentOptions,
    style: EffectiveStyle,
    substitutions: dict[str, str],
    page_size: tuple[float, float],
    *,
    blank: bool,
) -> None:
    from reportlab.lib.units import mm

    canvas_obj.saveState()
    margins = options.page.margins
    content_left = margins.left * mm
    content_right = page_size[0] - margins.right * mm
    content_center = (content_left + content_right) / 2
    page_num = canvas_obj.getPageNumber()
    body_font = resolve_font_family(style.body_font).regular

    if not blank:
        if header_footer.has_content(options.header):
            y = page_size[1] - margins.top * mm + 8
            _draw_header_footer_line(
                canvas_obj,
                options.header,
                y,
                content_left,
                content_center,
                content_right,
                page_num,
                substitutions,
                body_font,
                style.accent_color,
                style.text_color,
                -6,
            )
        if header_footer.has_content(options.footer):
            y = margins.bottom * mm - 16
            _draw_header_footer_line(
                canvas_obj,
                options.footer,
                y,
                content_left,
                content_center,
                content_right,
                page_num,
                substitutions,
                body_font,
                style.accent_color,
                style.text_color,
                12,
            )

    if options.watermark:
        _draw_watermark(canvas_obj, page_size, options.watermark)

    canvas_obj.restoreState()

    if options.pdf.metadata.keywords:
        canvas_obj.setKeywords(options.pdf.metadata.keywords)


def _make_on_page_callbacks(
    options: DocumentOptions,
    style: EffectiveStyle,
    substitutions: dict[str, str],
    page_size: tuple[float, float],
) -> tuple[Any, Any]:
    different_first = (
        header_footer.has_content(options.header) and options.header.different_first_page
    ) or (header_footer.has_content(options.footer) and options.footer.different_first_page)

    def on_first_page(canvas_obj: Any, _doc: Any) -> None:
        _draw_page_furniture(
            canvas_obj, options, style, substitutions, page_size, blank=different_first
        )

    def on_later_pages(canvas_obj: Any, _doc: Any) -> None:
        _draw_page_furniture(canvas_obj, options, style, substitutions, page_size, blank=False)

    return on_first_page, on_later_pages


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _toc_flowables(blocks: list[Block], toc_options: Any, styles: dict[str, Any]) -> list[Any]:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import PageBreak, Paragraph
    from reportlab.platypus.tableofcontents import TableOfContents

    has_heading = any(isinstance(b, HeadingBlock) and b.level <= toc_options.depth for b in blocks)
    if not has_heading:
        return []

    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            f"TOCLevel{level}",
            parent=styles["body"],
            leftIndent=level * 14,
            fontName=styles["body_font_name"],
        )
        for level in range(6)
    ]
    return [
        Paragraph(_escape_pdf_xml(toc_options.title), styles["title"]),
        toc,
        PageBreak(),
    ]


def render_pdf(title: str | None, markdown: str, options: DocumentOptions | None = None) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        NextPageTemplate,
        PageTemplate,
        Paragraph,
        Spacer,
    )

    if not (markdown or "").strip():
        raise ValueError("render_pdf: content must not be empty")

    options = options or DocumentOptions()
    style = resolve_effective_style(options)
    blocks = prepare_blocks(markdown, options)
    styles = _pdf_styles(style, options.tables)
    page_size = _resolve_page_size(options.page)
    margins = options.page.margins
    substitutions = {
        "title": title or options.cover.project or "",
        "date": options.cover.date,
        "version": options.cover.version,
    }

    story: list[Any] = []
    if options.cover.enabled:
        story.extend(_pdf_cover_flowables(options.cover, title, styles))
    elif title:
        story.append(Paragraph(_escape_pdf_xml(title), styles["title"]))
        story.append(Spacer(1, 12))

    toc_enabled = options.toc.enabled
    if toc_enabled:
        story.extend(_toc_flowables(blocks, options.toc, styles))

    for block in blocks:
        story.extend(_pdf_flowables_for_block(block, styles))

    frame = Frame(
        margins.left * mm,
        margins.bottom * mm,
        page_size[0] - (margins.left + margins.right) * mm,
        page_size[1] - (margins.top + margins.bottom) * mm,
        id="content",
    )
    on_first_page, on_later_pages = _make_on_page_callbacks(
        options, style, substitutions, page_size
    )

    heading_style_names = {f"DocHeading{level}" for level in range(1, 7)}
    bookmarks_enabled = options.pdf.bookmarks
    bookmark_counter = [0]

    class _DocTemplate(BaseDocTemplate):
        def afterFlowable(self, flowable: Any) -> None:
            style_name = getattr(getattr(flowable, "style", None), "name", None)
            if style_name not in heading_style_names:
                return
            level = int(style_name.removeprefix("DocHeading")) - 1
            text = flowable.getPlainText()

            if bookmarks_enabled:
                key = f"heading-{bookmark_counter[0]}"
                bookmark_counter[0] += 1
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level, closed=False)

            if toc_enabled and level < options.toc.depth:
                self.notify("TOCEntry", (level, text, self.page))

    buffer = io.BytesIO()
    document = _DocTemplate(
        buffer,
        pagesize=page_size,
        pageTemplates=[
            PageTemplate(id="first", frames=[frame], onPage=on_first_page),
            PageTemplate(id="later", frames=[frame], onPage=on_later_pages),
        ],
    )
    document.title = options.pdf.metadata.title or title or ""
    document.author = options.pdf.metadata.author
    document.subject = options.pdf.metadata.subject

    full_story = [NextPageTemplate("later"), *story]
    if toc_enabled:
        document.multiBuild(full_story, canvasmaker=NumberedCanvas)
    else:
        document.build(full_story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
