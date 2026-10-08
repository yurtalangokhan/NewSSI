from service.authored_documents.markdown_segments import (
    mermaid_segments,
    outline,
    segment_markdown,
)

DOC = """# Tedarikçi Onboarding

## 1. Amaç

Bu doküman adımları tanımlar.

## 2. Süreç akışı

```mermaid
flowchart LR
  A --> B

  B --> C
```

## 3. SLA

| Adım | Süre |
|---|---|
| Belge | 2 |

- madde bir
- madde iki
"""


def test_segments_are_fence_aware_and_labelled_by_nearest_heading() -> None:
    kinds = [(s.kind, s.label) for s in segment_markdown(DOC)]
    assert kinds == [
        ("heading", "Tedarikçi Onboarding"),
        ("heading", "1. Amaç"),
        ("paragraph", "1. Amaç"),
        ("heading", "2. Süreç akışı"),
        ("mermaid", "2. Süreç akışı"),
        ("heading", "3. SLA"),
        ("table", "3. SLA"),
        ("list", "3. SLA"),
    ]


def test_mermaid_segment_keeps_blank_lines_and_line_numbers() -> None:
    (block,) = mermaid_segments(DOC)
    assert block.text == "flowchart LR\n  A --> B\n\n  B --> C"
    assert block.start_line == 10  # first content line after the opening fence
    assert block.language == "mermaid"


def test_outline_lists_headings_with_lines() -> None:
    assert outline(DOC)[:2] == [
        {"line": 1, "level": 1, "text": "Tedarikçi Onboarding"},
        {"line": 3, "level": 2, "text": "1. Amaç"},
    ]


def test_unclosed_fence_runs_to_end_of_document() -> None:
    (block,) = segment_markdown("```mermaid\nflowchart LR\n  A --> B")
    assert block.kind == "mermaid"
    assert block.text == "flowchart LR\n  A --> B"


def test_empty_mermaid_fence_keeps_start_line_at_or_before_end_line() -> None:
    (closed,) = segment_markdown("```mermaid\n```")
    assert closed.text == ""
    assert closed.start_line <= closed.end_line
    assert (closed.start_line, closed.end_line) == (2, 2)

    (unclosed,) = segment_markdown("```mermaid")
    assert unclosed.text == ""
    assert unclosed.start_line <= unclosed.end_line
    assert (unclosed.start_line, unclosed.end_line) == (2, 2)
