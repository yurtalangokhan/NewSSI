"""Let a non-LLM flow node describe what it did in the timeline.

LLM stages stream their answer text, which the stream service folds into the
stage's timeline entry. Data and retrieval nodes (KnowledgeBase, Graph*,
DocumentContext, …) produce no answer text, so their timeline stage
expanded to nothing — a viewer saw a step that appeared to have done
nothing.

A retrieval node calls :func:`report_stage_evidence` with what it retrieved;
the evidence is recorded and the stream service shows it as the stage's
knowledge card (chunks or subgraph), live and after a refresh. Other nodes —
and a retrieval node whose evidence could not be recorded — call
:func:`report_stage_output` with a short human-readable summary instead, which
the stream service emits as a ``flow_stage_output_delta``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from core.observability.logger import get_logger
from schemas.knowledge_evidence import KnowledgeEvidence
from service.knowledge_evidence.factory import build_knowledge_evidence_recorder

logger = get_logger(__name__)


class EvidenceRecorder(Protocol):
    async def record(self, evidence: KnowledgeEvidence, *, thread_id: UUID | None = None) -> UUID | None: ...


def _stream_writer() -> Callable[[dict[str, Any]], None] | None:
    """The running graph's custom stream writer, or ``None`` outside a streamed run."""
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except Exception as exc:
        logger.debug("no stream writer: %s", exc)
        return None


def report_stage_output(node_id: str, summary: str) -> None:
    """Emit a stage summary for ``node_id`` if a stream writer is active.

    Safe to call unconditionally: outside a streamed run (tests, tool-mode
    invocation) there is no writer and this is a no-op.
    """
    if not summary:
        return
    writer = _stream_writer()
    if writer:
        writer({"type": "flow_stage_summary", "node_id": node_id, "summary": summary})


@dataclass
class ComponentEvidence:
    """Evidence ids a node reported while it ran as an agent tool."""

    ids: list[UUID] = field(default_factory=list)


_component_evidence: ContextVar[ComponentEvidence | None] = ContextVar("component_evidence", default=None)


@contextmanager
def capture_component_evidence() -> Iterator[ComponentEvidence]:
    """Collect a node's evidence for the tool call wrapping it.

    A retrieval node running as an agent tool must not announce a stage card:
    the tool call is the step, so its ToolMessage carries the evidence instead.
    """
    sink = ComponentEvidence()
    token = _component_evidence.set(sink)
    try:
        yield sink
    finally:
        _component_evidence.reset(token)


async def report_stage_evidence(
    node_id: str,
    evidence: KnowledgeEvidence,
    *,
    recorder: EvidenceRecorder | None = None,
) -> bool:
    """Record what a retrieval node retrieved and show it as the stage's card.

    Inside :func:`capture_component_evidence` the id goes to the capturing
    tool call instead of the stream. Returns ``False`` when there is nowhere
    to show it or the evidence could not be recorded; the node then falls back
    to a text summary.
    """
    sink = _component_evidence.get()
    writer = None if sink is not None else _stream_writer()
    if sink is None and not writer:
        return False
    evidence_id = await (recorder or build_knowledge_evidence_recorder()).record(evidence)
    if evidence_id is None:
        return False
    if sink is not None:
        sink.ids.append(evidence_id)
        return True
    writer(
        {
            "type": "flow_stage_evidence",
            "node_id": node_id,
            "evidence_id": str(evidence_id),
            "tool": evidence.tool,
            "query": evidence.query,
        }
    )
    return True


def summarise_chunks(chunks: list[Any], *, top_k: int, threshold: float | None) -> str:
    """One line per retrieved chunk: source, score, a short preview."""
    header = f"{len(chunks)} parça getirildi (top_k={top_k}"
    if threshold is not None:
        header += f", eşik={threshold:g}"
    header += ")"
    if not chunks:
        return header + " — eşleşen belge yok."
    lines = [header]
    for c in chunks[:top_k]:
        src = ""
        meta = getattr(c, "metadata", None) or {}
        if isinstance(meta, dict):
            src = str(meta.get("source") or meta.get("title") or "")
        score = getattr(c, "score", None)
        score_txt = f"skor={score:.2f} " if isinstance(score, (int, float)) else ""
        text = (getattr(c, "text", "") or "").strip().replace("\n", " ")
        lines.append(f"- {('[' + src + '] ') if src else ''}{score_txt}{text[:160]}")
    return "\n".join(lines)


def summarise_graph_result(payload: Any, *, label: str) -> str:
    """Node/edge counts for a graph-RAG result, or a compact dict digest."""
    if isinstance(payload, dict):
        nodes = payload.get("nodes")
        edges = payload.get("edges")
        if isinstance(nodes, list) or isinstance(edges, list):
            n = len(nodes) if isinstance(nodes, list) else 0
            e = len(edges) if isinstance(edges, list) else 0
            return f"{label}: {n} düğüm, {e} kenar"
        # stats-style dict
        parts = [
            f"{k}={v}" for k, v in payload.items() if isinstance(v, (int, float, str)) and not str(k).startswith("_")
        ]
        if parts:
            return f"{label}: " + ", ".join(parts[:8])
    if isinstance(payload, list):
        return f"{label}: {len(payload)} sonuç"
    return f"{label}: sonuç alındı"
