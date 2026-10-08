from core.types.authored_documents import BlockChange, SourceFormat
from service.authored_documents.revision_stats import compute_stats

OLD = "## 1. Amaç\n\nMetin.\n\n## 3. SLA\n\n| A | B |\n|---|---|\n| x | 2 |\n"
NEW = (
    "## 1. Amaç\n\nMetin.\n\n## 3. SLA\n\n| A | B |\n|---|---|\n| x | 1 |\n| y | 3 |\n\n"
    "## 4. Entegrasyon\n\n```mermaid\nsequenceDiagram\n  A->>B: x\n```\n"
)


def test_line_counts() -> None:
    stats = compute_stats(OLD, NEW, SourceFormat.MARKDOWN)
    assert (stats.added, stats.removed) == (9, 1)


def test_block_changes_are_labelled() -> None:
    stats = compute_stats(OLD, NEW, SourceFormat.MARKDOWN)
    assert stats.changes == (
        BlockChange("table", "3. SLA", "modified"),
        BlockChange("heading", "4. Entegrasyon", "added"),
        BlockChange("mermaid", "4. Entegrasyon", "added"),
    )


def test_non_markdown_sources_only_count_lines() -> None:
    stats = compute_stats('{"a": 1}', '{"a": 2}', SourceFormat.JSON)
    assert (stats.added, stats.removed, stats.changes) == (1, 1, ())
