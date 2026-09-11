import json
import re
import uuid

from error_contract import ApplicationError
from i18n import t
from langchain_community.document_loaders.parsers import BS4HTMLParser, PDFMinerParser
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_core.documents.base import Blob, Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langconnect.models.documents import FileUploadDTO
from langconnect.observability import get_logger

LOGGER = get_logger(__name__)

# ── Max upload size: 200 MB ──────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


# ── Custom parsers for best embedding quality ────────────────────────────


class _CSVToTextParser:
    """Parse CSV/TSV into one document per row formatted as key: value pairs.

    Row-based output produces short, semantically dense chunks that embed
    far better than raw delimited lines.
    """

    def __init__(self, delimiter: str = ",") -> None:
        self._delimiter = delimiter

    def lazy_parse(self, blob: Blob):
        import csv
        import io

        text = blob.as_string()
        reader = csv.DictReader(io.StringIO(text), delimiter=self._delimiter)
        for i, row in enumerate(reader):
            content = "\n".join(
                f"{k}: {v}" for k, v in row.items() if v is not None and v.strip()
            )
            if content:
                yield Document(page_content=content, metadata={"row": i})

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


class _JSONToTextParser:
    """Flatten JSON objects/arrays into readable key-value text.

    Produces clean prose-like output that embeds much better than raw JSON
    syntax with braces and quotes.
    """

    @staticmethod
    def _flatten(obj, prefix: str = "") -> list[str]:
        lines: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    lines.extend(_JSONToTextParser._flatten(v, key))
                elif v is not None:
                    lines.append(f"{key}: {v}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                lines.extend(_JSONToTextParser._flatten(item, f"{prefix}[{i}]"))
        elif obj is not None:
            lines.append(f"{prefix}: {obj}" if prefix else str(obj))
        return lines

    def lazy_parse(self, blob: Blob):
        data = json.loads(blob.as_string())
        if isinstance(data, list):
            for i, item in enumerate(data):
                content = "\n".join(self._flatten(item))
                if content:
                    yield Document(page_content=content, metadata={"index": i})
        else:
            content = "\n".join(self._flatten(data))
            if content:
                yield Document(page_content=content, metadata={})

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


class _ExcelToTextParser:
    """Parse XLSX/XLS into row-based key-value text (same strategy as CSV).

    Each sheet is processed independently. Row-based output ensures each
    chunk represents a single record — ideal for embedding. Merged cells are
    filled from their top-left value (openpyxl otherwise reports the rest of
    the merged range as blank), and leading blank rows are skipped so a
    banner/title row above the real header doesn't get treated as columns.

    Loaded without `read_only` because openpyxl's read-only worksheets don't
    expose `merged_cells`.
    """

    def lazy_parse(self, blob: Blob):
        import io

        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(blob.as_bytes()), data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = [list(row) for row in ws.iter_rows(values_only=True)]
            if len(rows) < 2:
                continue

            self._fill_merged_cells(ws, rows)

            header_offset = next(
                (i for i, row in enumerate(rows) if any(v is not None for v in row)),
                len(rows),
            )
            if len(rows) - header_offset < 2:
                continue

            headers = [
                str(h) if h is not None else f"col_{i}"
                for i, h in enumerate(rows[header_offset])
            ]
            for row_idx, row in enumerate(
                rows[header_offset + 1 :], start=header_offset + 2
            ):
                content = "\n".join(
                    f"{headers[j]}: {cell}"
                    for j, cell in enumerate(row)
                    if j < len(headers) and cell is not None and str(cell).strip()
                )
                if content:
                    yield Document(
                        page_content=content,
                        metadata={"sheet": sheet_name, "row": row_idx},
                    )
        wb.close()

    @staticmethod
    def _fill_merged_cells(ws, rows: list[list]) -> None:
        for merged_range in ws.merged_cells.ranges:
            top_left = rows[merged_range.min_row - 1][merged_range.min_col - 1]
            if top_left is None:
                continue
            for r in range(merged_range.min_row, merged_range.max_row + 1):
                for c in range(merged_range.min_col, merged_range.max_col + 1):
                    if rows[r - 1][c - 1] is None:
                        rows[r - 1][c - 1] = top_left

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


class _PPTXToTextParser:
    """Parse PowerPoint presentations into one document per slide.

    Slide-level chunking preserves the author's logical grouping of
    information, which produces more coherent embeddings than paragraph-level
    splitting across slide boundaries. Grouped shapes are walked recursively
    (their text isn't reachable from the top-level shape list otherwise), and
    speaker notes are appended since they often carry the explanation for
    what's on the slide.
    """

    def lazy_parse(self, blob: Blob):
        import io

        from pptx import Presentation

        prs = Presentation(io.BytesIO(blob.as_bytes()))
        for slide_num, slide in enumerate(prs.slides, start=1):
            texts: list[str] = []
            self._collect_shape_text(slide.shapes, texts)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    texts.append(f"Speaker notes: {notes}")
            if texts:
                yield Document(
                    page_content="\n".join(texts),
                    metadata={"slide": slide_num},
                )

    @classmethod
    def _collect_shape_text(cls, shapes, texts: list[str]) -> None:
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                cls._collect_shape_text(shape.shapes, texts)
                continue
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        texts.append(text)
            if shape.has_table:
                table = shape.table
                for row in table.rows:
                    row_text = " | ".join(
                        cell.text.strip() for cell in row.cells if cell.text.strip()
                    )
                    if row_text:
                        texts.append(row_text)

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


class _DocxToTextParser:
    """Parse Word documents into structure-aware markdown text.

    Uses `python-docx` (already a project dependency) instead of langchain's
    `MsWordParser`/`UnstructuredWordDocumentLoader`, which require installing
    the heavy `unstructured` package. Content is walked in actual document
    order via `iter_inner_content` (not paragraphs-then-tables, which loses
    interleaving), headings become markdown headers, and tables become
    markdown tables so structure survives into the embedded text.
    """

    def lazy_parse(self, blob: Blob):
        import io

        from docx import Document as DocxDocument
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = DocxDocument(io.BytesIO(blob.as_bytes()))
        blocks: list[str] = []
        for item in doc.iter_inner_content():
            if isinstance(item, Paragraph):
                block = self._paragraph_to_markdown(item)
                if block:
                    blocks.append(block)
            elif isinstance(item, Table):
                block = self._table_to_markdown(item)
                if block:
                    blocks.append(block)
        if blocks:
            yield Document(page_content="\n\n".join(blocks), metadata={})

    @staticmethod
    def _paragraph_to_markdown(paragraph) -> str:
        text = paragraph.text.strip()
        if not text:
            return ""
        style = paragraph.style.name if paragraph.style else ""
        if style == "Title":
            return f"# {text}"
        if style.startswith("Heading"):
            digits = "".join(c for c in style if c.isdigit())
            level = min(int(digits), 6) if digits else 1
            return f"{'#' * level} {text}"
        return text

    @staticmethod
    def _table_to_markdown(table) -> str:
        rows = [
            [cell.text.strip().replace("\n", " ") for cell in row.cells]
            for row in table.rows
        ]
        rows = [row for row in rows if any(row)]
        if not rows:
            return ""
        header, *body = rows
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        lines.extend("| " + " | ".join(row) + " |" for row in body)
        return "\n".join(lines)

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


# ── PDF cleaning utilities ────────────────────────────────────────────────

BULLET_CHARS: set[str] = {
    "•",
    "·",
    "▪",
    "▫",
    "◦",
    "‣",
    "\u2043",
    "∙",
    "●",
    "○",
    "■",
    "□",
    "\u2013",
    "\u2014",
    "*",
    "\uf0a7",
    "\uf0b7",
    "\uf0a8",
    "\uf0d8",
    "\uf0fc",
    "\u27a1",
    "\u2794",
}


def _is_standalone_bullet(stripped: str) -> bool:
    return stripped in BULLET_CHARS or bool(
        re.match(r"^(\d+|[a-zA-Z]|\([0-9a-zA-Z]+\))[\.\)]$", stripped)
    )


def _should_join_lines(prev: str, curr: str) -> bool:
    if not prev or not curr:
        return False
    if prev.endswith((".", "!", "?", ":", ";")):
        return False
    if re.match(r"^\d+[\.\)]\s+", curr):
        return False
    if prev.endswith((",", "-", "—")):
        return True
    return curr[0].islower()


def clean_pdf_text(text: str) -> str:
    """Clean PDF extracted text by reconstructing bullet lists and soft line breaks."""
    if not text:
        return ""
    raw_lines = text.splitlines()
    parsed_lines: list[tuple[str, str, str]] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            parsed_lines.append(("EMPTY", "", ""))
        elif _is_standalone_bullet(stripped):
            parsed_lines.append(("BULLET_ONLY", stripped, ""))
        else:
            first_char = stripped[0]
            if first_char in BULLET_CHARS:
                content = stripped[1:].lstrip()
                parsed_lines.append(("BULLET_TEXT", first_char, content))
            else:
                parsed_lines.append(("TEXT", "", stripped))

    output_blocks: list[tuple[str, str]] = []
    i = 0
    n = len(parsed_lines)
    while i < n:
        line_type, b_char, content = parsed_lines[i]
        if line_type == "EMPTY":
            output_blocks.append(("EMPTY", ""))
            i += 1
            continue
        if line_type == "BULLET_TEXT":
            output_blocks.append(("LINE", f"{b_char} {content}"))
            i += 1
            continue
        if line_type == "BULLET_ONLY":
            bullet_stack: list[str] = []
            j = i
            while j < n:
                curr_type, curr_bchar, _ = parsed_lines[j]
                if curr_type == "BULLET_ONLY":
                    bullet_stack.append(curr_bchar)
                    j += 1
                elif curr_type == "EMPTY":
                    j += 1
                else:
                    break
            text_lines: list[str] = []
            k = j
            while k < n and len(text_lines) < len(bullet_stack):
                curr_type, curr_bchar, curr_content = parsed_lines[k]
                if curr_type == "TEXT":
                    text_lines.append(curr_content)
                    k += 1
                elif curr_type in ("BULLET_TEXT", "BULLET_ONLY"):
                    break
                elif curr_type == "EMPTY":
                    k += 1
            matched_count = min(len(bullet_stack), len(text_lines))
            for m in range(matched_count):
                bullet_symbol = bullet_stack[m]
                output_blocks.append(("LINE", f"{bullet_symbol} {text_lines[m]}"))
            i = k
            continue
        if line_type == "TEXT":
            output_blocks.append(("LINE", content))
            i += 1

    final_lines: list[str] = []
    for kind, val in output_blocks:
        if kind == "EMPTY":
            if final_lines and final_lines[-1] != "":
                final_lines.append("")
        elif (
            final_lines
            and final_lines[-1] != ""
            and not final_lines[-1].startswith(tuple(BULLET_CHARS))
            and not val.startswith(tuple(BULLET_CHARS))
            and _should_join_lines(final_lines[-1], val)
        ):
            final_lines[-1] = final_lines[-1] + " " + val
        elif (
            final_lines
            and len(final_lines) >= 2
            and final_lines[-1] == ""
            and final_lines[-2] != ""
            and not final_lines[-2].startswith(tuple(BULLET_CHARS))
            and not val.startswith(tuple(BULLET_CHARS))
            and _should_join_lines(final_lines[-2], val)
        ):
            final_lines.pop()
            final_lines[-1] = final_lines[-1] + " " + val
        else:
            final_lines.append(val)

    result = "\n".join(final_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


class _PDFToTextParser:
    """Parse PDF documents using PDFMinerParser with clean_pdf_text post-processor."""

    def __init__(self) -> None:
        self._parser = PDFMinerParser()

    def lazy_parse(self, blob: Blob):
        for doc in self._parser.lazy_parse(blob):
            cleaned_content = clean_pdf_text(doc.page_content)
            yield Document(page_content=cleaned_content, metadata=doc.metadata)

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


# ── Handler registry ─────────────────────────────────────────────────────
# Each MIME type is mapped to the parser that produces the cleanest text
# for high-quality embeddings.

HANDLERS = {
    # ── Documents ──
    "application/pdf": _PDFToTextParser(),
    "application/msword": _DocxToTextParser(),  # .doc (legacy binary format is not
    # supported by python-docx; only modern .doc saved as OOXML will parse)
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        _DocxToTextParser()  # .docx
    ),
    # ── Presentations ──
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        _PPTXToTextParser()  # .pptx
    ),
    # ── Spreadsheets / tabular ──
    "text/csv": _CSVToTextParser(),  # .csv
    "text/tab-separated-values": _CSVToTextParser(delimiter="\t"),  # .tsv
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        _ExcelToTextParser()  # .xlsx
    ),
    "application/vnd.ms-excel": _ExcelToTextParser(),  # .xls
    # ── Markup / text ──
    "text/plain": TextParser(),  # .txt
    "text/markdown": TextParser(),  # .md
    "text/html": BS4HTMLParser(),  # .html
    "application/xhtml+xml": BS4HTMLParser(),  # .xhtml
    "text/xml": BS4HTMLParser(),  # .xml
    "application/xml": BS4HTMLParser(),  # .xml
    # ── Structured data ──
    "application/json": _JSONToTextParser(),  # .json
    # ── Rich text ──
    "application/rtf": TextParser(),  # .rtf
    "text/rtf": TextParser(),  # .rtf
    # ── Email ──
    "message/rfc822": TextParser(),  # .eml
}

SUPPORTED_MIMETYPES = sorted(HANDLERS.keys())

MIMETYPE_BASED_PARSER = MimeTypeBasedParser(
    handlers=HANDLERS,
    fallback_parser=None,
)

# Text Splitter
TEXT_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


async def process_document(
    file: FileUploadDTO, metadata: dict | None = None
) -> list[Document]:
    """Process an uploaded file into LangChain documents.

    Args:
        file: Framework-agnostic upload DTO carrying filename, content type,
            size, and raw bytes.  Built by the API layer from a FastAPI
            ``UploadFile`` so that this module has no framework dependency.
        metadata: Optional per-file metadata merged into every resulting
            document.
    """
    # Generate a unique ID for this file processing instance
    file_id = uuid.uuid4()

    contents = file.content

    # ── Enforce 200 MB file-size limit ────────────────────────────────
    if len(contents) > MAX_FILE_SIZE_BYTES:
        size_mb = len(contents) / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        raise ApplicationError(
            status_code=413,
            code="document.file_too_large",
            message=t(
                "document.file_too_large",
                filename=file.filename,
                size_mb=f"{size_mb:.1f}",
                limit_mb=f"{limit_mb:.0f}",
            ),
            details={
                "filename": file.filename or "",
                "size_mb": f"{size_mb:.1f}",
                "limit_mb": f"{limit_mb:.0f}",
            },
        )

    blob = Blob(data=contents, mimetype=file.content_type or "text/plain")

    docs = MIMETYPE_BASED_PARSER.parse(blob)

    # Add provided metadata to each document
    if metadata:
        for doc in docs:
            # Ensure metadata attribute exists and is a dict
            if not hasattr(doc, "metadata") or not isinstance(doc.metadata, dict):
                doc.metadata = {}
            # Update with provided metadata, preserving existing keys if not overridden
            doc.metadata.update(metadata)

    # Split documents
    split_docs = TEXT_SPLITTER.split_documents(docs)

    import math

    # Add the generated file_id and chunk stats to all split documents' metadata
    total_chunks = len(split_docs)
    total_chars = 0
    total_tokens = 0

    # First pass to calculate totals
    for split_doc in split_docs:
        content_len = len(split_doc.page_content)
        tokens = math.ceil(content_len / 4)
        total_chars += content_len
        total_tokens += tokens

    avg_chars = round(total_chars / total_chunks) if total_chunks > 0 else 0
    avg_tokens = round(total_tokens / total_chunks) if total_chunks > 0 else 0

    for split_doc in split_docs:
        if not hasattr(split_doc, "metadata") or not isinstance(
            split_doc.metadata, dict
        ):
            split_doc.metadata = {}  # Initialize if it doesn't exist

        # Identity
        split_doc.metadata["file_id"] = str(
            file_id
        )  # Store as string for compatibility

        # Individual chunk stats
        content_len = len(split_doc.page_content)
        split_doc.metadata["char_count"] = content_len
        split_doc.metadata["token_count"] = math.ceil(content_len / 4)

        # File aggregated stats
        split_doc.metadata["file_total_chunks"] = total_chunks
        split_doc.metadata["file_avg_chars"] = avg_chars
        split_doc.metadata["file_avg_tokens"] = avg_tokens

    return split_docs
