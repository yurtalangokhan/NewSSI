"""Raw OOXML fragments python-docx has no high-level API for.

Hyperlinks, paragraph/cell shading and paragraph borders need hand-built XML
elements; TOC fields, `updateFields` and watermarks join this module once
the DOCX page scaffolding phase needs them.
"""

from __future__ import annotations

from typing import Any

from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph


def _build_hyperlink_run(text: str, color: str) -> Any:
    hyperlink = OxmlElement("w:hyperlink")

    run = OxmlElement("w:r")
    run_properties = OxmlElement("w:rPr")
    color_el = OxmlElement("w:color")
    color_el.set(qn("w:val"), color)
    run_properties.append(color_el)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_properties.append(underline)
    run.append(run_properties)

    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)

    hyperlink.append(run)
    return hyperlink


def add_hyperlink_run(paragraph: Paragraph, text: str, url: str, color: str = "0563C1") -> None:
    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)

    hyperlink = _build_hyperlink_run(text, color)
    hyperlink.set(qn("r:id"), r_id)
    paragraph._p.append(hyperlink)  # noqa: SLF001


def add_internal_hyperlink_run(
    paragraph: Paragraph, text: str, anchor: str, color: str = "0563C1"
) -> None:
    """A hyperlink to a bookmark elsewhere in the same document (`add_bookmark`)
    rather than an external URL — used for clickable table-of-contents entries."""
    hyperlink = _build_hyperlink_run(text, color)
    hyperlink.set(qn("w:anchor"), anchor)
    paragraph._p.append(hyperlink)  # noqa: SLF001


def add_bookmark(paragraph: Paragraph, name: str, bookmark_id: int) -> None:
    """Wrap `paragraph` in a named bookmark so `add_internal_hyperlink_run`
    elsewhere in the document can link straight to it."""
    p_pr = paragraph._p.get_or_add_pPr()  # noqa: SLF001
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    p_pr.addnext(start)

    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.append(end)  # noqa: SLF001


def add_paragraph_border(paragraph: Paragraph, side: str = "bottom", color: str = "999999") -> None:
    paragraph_properties = paragraph._p.get_or_add_pPr()  # noqa: SLF001
    border = OxmlElement("w:pBdr")
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), "6")
    edge.set(qn("w:space"), "1")
    edge.set(qn("w:color"), color)
    border.append(edge)
    paragraph_properties.append(border)


def add_horizontal_rule(paragraph: Paragraph, color: str = "999999") -> None:
    add_paragraph_border(paragraph, side="bottom", color=color)


def enable_update_fields(document: Any) -> None:
    """Set `<w:updateFields w:val="true"/>` so Word recalculates fields (TOC,
    PAGE, NUMPAGES) on open instead of showing whatever was cached at
    generation time."""
    settings = document.settings.element
    if settings.find(qn("w:updateFields")) is not None:
        return
    element = OxmlElement("w:updateFields")
    element.set(qn("w:val"), "true")
    settings.append(element)


def add_field_begin(paragraph: Paragraph, instruction: str) -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    paragraph.add_run()._r.append(begin)  # noqa: SLF001

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    paragraph.add_run()._r.append(instr)  # noqa: SLF001

    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    paragraph.add_run()._r.append(separate)  # noqa: SLF001


def add_field_end(paragraph: Paragraph) -> None:
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(end)  # noqa: SLF001


def add_field_run(paragraph: Paragraph, field_code: str, cached_value: str = "1") -> None:
    """Insert a Word field (e.g. PAGE, NUMPAGES) as begin/instrText/separate/
    cached-value/end runs — the same structure Word itself writes."""
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    paragraph.add_run()._r.append(begin)  # noqa: SLF001

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {field_code} "
    paragraph.add_run()._r.append(instr)  # noqa: SLF001

    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    paragraph.add_run()._r.append(separate)  # noqa: SLF001

    paragraph.add_run(cached_value)

    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph.add_run()._r.append(end)  # noqa: SLF001


def _shading_element(color: str) -> Any:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color.lstrip("#"))
    return shd


def shade_cell(cell: _Cell, color: str) -> None:
    cell._tc.get_or_add_tcPr().append(_shading_element(color))  # noqa: SLF001


def shade_paragraph(paragraph: Paragraph, color: str) -> None:
    paragraph._p.get_or_add_pPr().append(_shading_element(color))  # noqa: SLF001


def add_table_border(table: Table, side: str, color: str = "999999") -> None:
    borders = table._tbl.tblPr.find(qn("w:tblBorders"))  # noqa: SLF001
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        table._tbl.tblPr.append(borders)  # noqa: SLF001
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), "6")
    edge.set(qn("w:space"), "1")
    edge.set(qn("w:color"), color)
    borders.append(edge)
