import json
import logging
import uuid

from fastapi import HTTPException, UploadFile
from langchain_community.document_loaders.parsers import BS4HTMLParser, PDFMinerParser
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_community.document_loaders.parsers.msword import MsWordParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_core.documents.base import Blob, Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

LOGGER = logging.getLogger(__name__)

# ── Max upload size: 200 MB ──────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


# ── Custom parsers for best embedding quality ────────────────────────────

class _CSVToTextParser:
    """Parse CSV into one document per row formatted as key: value pairs.

    Row-based output produces short, semantically dense chunks that embed
    far better than raw comma-separated lines.
    """

    def lazy_parse(self, blob: Blob):  # noqa: ANN201
        import csv
        import io

        text = blob.as_string()
        reader = csv.DictReader(io.StringIO(text))
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
        else:
            if obj is not None:
                lines.append(f"{prefix}: {obj}" if prefix else str(obj))
        return lines

    def lazy_parse(self, blob: Blob):  # noqa: ANN201
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
    chunk represents a single record — ideal for embedding.
    """

    def lazy_parse(self, blob: Blob):  # noqa: ANN201
        import openpyxl
        import io

        wb = openpyxl.load_workbook(io.BytesIO(blob.as_bytes()), read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if len(rows) < 2:
                continue
            headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
            for row_idx, row in enumerate(rows[1:], start=1):
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

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


class _PPTXToTextParser:
    """Parse PowerPoint presentations into one document per slide.

    Slide-level chunking preserves the author's logical grouping of
    information, which produces more coherent embeddings than paragraph-level
    splitting across slide boundaries.
    """

    def lazy_parse(self, blob: Blob):  # noqa: ANN201
        from pptx import Presentation
        import io

        prs = Presentation(io.BytesIO(blob.as_bytes()))
        for slide_num, slide in enumerate(prs.slides, start=1):
            texts: list[str] = []
            for shape in slide.shapes:
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
            if texts:
                yield Document(
                    page_content="\n".join(texts),
                    metadata={"slide": slide_num},
                )

    def parse(self, blob: Blob) -> list[Document]:
        return list(self.lazy_parse(blob))


# ── Handler registry ─────────────────────────────────────────────────────
# Each MIME type is mapped to the parser that produces the cleanest text
# for high-quality embeddings.

HANDLERS = {
    # ── Documents ──
    "application/pdf": PDFMinerParser(),
    "application/msword": MsWordParser(),                                       # .doc
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        MsWordParser()                                                          # .docx
    ),
    # ── Presentations ──
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        _PPTXToTextParser()                                                     # .pptx
    ),
    # ── Spreadsheets / tabular ──
    "text/csv": _CSVToTextParser(),                                             # .csv
    "text/tab-separated-values": _CSVToTextParser(),                            # .tsv
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        _ExcelToTextParser()                                                    # .xlsx
    ),
    "application/vnd.ms-excel": _ExcelToTextParser(),                           # .xls
    # ── Markup / text ──
    "text/plain": TextParser(),                                                 # .txt
    "text/markdown": TextParser(),                                              # .md
    "text/html": BS4HTMLParser(),                                               # .html
    "application/xhtml+xml": BS4HTMLParser(),                                   # .xhtml
    "text/xml": BS4HTMLParser(),                                                # .xml
    "application/xml": BS4HTMLParser(),                                         # .xml
    # ── Structured data ──
    "application/json": _JSONToTextParser(),                                    # .json
    # ── Rich text ──
    "application/rtf": TextParser(),                                            # .rtf
    "text/rtf": TextParser(),                                                   # .rtf
    # ── Email ──
    "message/rfc822": TextParser(),                                             # .eml
}

SUPPORTED_MIMETYPES = sorted(HANDLERS.keys())

MIMETYPE_BASED_PARSER = MimeTypeBasedParser(
    handlers=HANDLERS,
    fallback_parser=None,
)

# Text Splitter
TEXT_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


async def process_document(
    file: UploadFile, metadata: dict | None = None
) -> list[Document]:
    """Process an uploaded file into LangChain documents."""
    # Generate a unique ID for this file processing instance
    file_id = uuid.uuid4()

    contents = await file.read()

    # ── Enforce 200 MB file-size limit ────────────────────────────────
    if len(contents) > MAX_FILE_SIZE_BYTES:
        size_mb = len(contents) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File '{file.filename}' is {size_mb:.1f} MB which exceeds "
                f"the 200 MB upload limit."
            ),
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
        split_doc.metadata["file_id"] = str(file_id)  # Store as string for compatibility
        
        # Individual chunk stats
        content_len = len(split_doc.page_content)
        split_doc.metadata["char_count"] = content_len
        split_doc.metadata["token_count"] = math.ceil(content_len / 4)

        # File aggregated stats
        split_doc.metadata["file_total_chunks"] = total_chunks
        split_doc.metadata["file_avg_chars"] = avg_chars
        split_doc.metadata["file_avg_tokens"] = avg_tokens

    return split_docs
