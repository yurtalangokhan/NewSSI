"""A ReportLab canvas that defers `{pages}`-dependent drawing.

ReportLab renders one page at a time and has no idea how many pages the
finished document will have until the very end. `showPage()` is overridden
to snapshot each page's state instead of flushing it immediately; `save()`
then replays every page once the true count is known, drawing whatever was
queued via `add_deferred_draw` (see `pdf_header_footer.needs_deferred_page_count`)
with `{pages}` finally substituted. This is the standard ReportLab
"NumberedCanvas" recipe, adapted to draw arbitrary left/center/right text
instead of a single fixed "Page X of Y" string.
"""

from __future__ import annotations

from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as reportlab_canvas

_DRAW_METHOD_BY_ALIGNMENT = {
    "left": "drawString",
    "center": "drawCentredString",
    "right": "drawRightString",
}


class NumberedCanvas(reportlab_canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self._pending_deferred_draws: list[tuple[str, float, float, str, str, float, str]] = []

    def add_deferred_draw(
        self,
        template: str,
        x: float,
        y: float,
        align: str,
        font_name: str,
        font_size: float,
        color_hex: str,
    ) -> None:
        self._pending_deferred_draws.append(
            (template, x, y, align, font_name, font_size, color_hex)
        )

    def showPage(self) -> None:  # noqa: N802 - overriding ReportLab's camelCase API
        self._saved_page_states.append(dict(self.__dict__))
        self._pending_deferred_draws = []
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            for template, x, y, align, font_name, font_size, color_hex in state[
                "_pending_deferred_draws"
            ]:
                text = template.replace("{pages}", str(total_pages))
                self.setFont(font_name, font_size)
                self.setFillColor(HexColor(color_hex))
                draw = getattr(self, _DRAW_METHOD_BY_ALIGNMENT[align])
                draw(x, y, text)
            reportlab_canvas.Canvas.showPage(self)
        reportlab_canvas.Canvas.save(self)
