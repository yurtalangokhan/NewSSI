"""Human-readable stage summaries for non-LLM flow nodes.

Data and retrieval nodes produce no answer text, so their timeline stage
expanded to nothing. These build the one-line-per-result summary the stream
service attributes to the node's open stage.
"""

from __future__ import annotations

import pytest

from agents.graphs.stage_report import (
    report_stage_output,
    summarise_chunks,
    summarise_graph_result,
)
from integrations.rag_client import RagChunk


def test_summarise_chunks_lists_source_score_and_preview():
    chunks = [
        RagChunk(
            text="Türksat 5A Falcon 9 ile fırlatıldı.",
            score=0.72,
            metadata={"source": "tarihce.md"},
        ),
        RagChunk(text="1994 kaza.", score=0.55, metadata={"source": "wiki"}),
    ]
    out = summarise_chunks(chunks, top_k=5, threshold=0.3)
    assert "2 parça getirildi (top_k=5, eşik=0.3)" in out
    assert "[tarihce.md] skor=0.72 Türksat 5A Falcon 9" in out
    assert "[wiki] skor=0.55 1994 kaza." in out


def test_summarise_chunks_handles_empty_and_no_threshold():
    assert "eşleşen belge yok" in summarise_chunks([], top_k=3, threshold=None)
    assert "eşik=" not in summarise_chunks([], top_k=3, threshold=None)


def test_summarise_chunks_caps_at_top_k():
    chunks = [RagChunk(text=f"c{i}", score=0.9) for i in range(10)]
    out = summarise_chunks(chunks, top_k=3, threshold=None)
    # header says 10, but only 3 preview lines
    assert out.startswith("10 parça getirildi")
    assert out.count("\n") == 3


def test_summarise_graph_result_counts_nodes_and_edges():
    assert (
        summarise_graph_result({"nodes": [1, 2, 3], "edges": [1]}, label="Graf arama")
        == "Graf arama: 3 düğüm, 1 kenar"
    )


def test_summarise_graph_result_digests_a_stats_dict():
    out = summarise_graph_result(
        {"node_count": 158, "edge_count": 173, "_internal": "x"}, label="İstatistik"
    )
    assert out == "İstatistik: node_count=158, edge_count=173"


def test_summarise_graph_result_handles_a_bare_list():
    assert summarise_graph_result([1, 2], label="X") == "X: 2 sonuç"


def test_report_stage_output_is_a_noop_without_a_stream_writer():
    # Outside a streamed run there is no writer; must not raise.
    report_stage_output("n_kb", "5 parça getirildi")
    report_stage_output("n_kb", "")


class _FakeRecorder:
    def __init__(self, evidence_id=None):
        self.evidence_id = evidence_id
        self.recorded = []

    async def record(self, evidence, *, thread_id=None):
        self.recorded.append(evidence)
        return self.evidence_id


def _evidence():
    from schemas.knowledge_evidence import EvidenceKind, KnowledgeEvidence

    return KnowledgeEvidence(kind=EvidenceKind.DOCUMENT, tool="document_search", query="izin devri")


@pytest.mark.asyncio
async def test_report_stage_evidence_records_and_announces_the_evidence(monkeypatch):
    from uuid import uuid4

    from agents.graphs import stage_report

    events = []
    evidence_id = uuid4()
    recorder = _FakeRecorder(evidence_id)
    monkeypatch.setattr(stage_report, "_stream_writer", lambda: events.append)

    reported = await stage_report.report_stage_evidence("search-1", _evidence(), recorder=recorder)

    assert reported is True
    assert recorder.recorded == [_evidence()]
    assert events == [
        {
            "type": "flow_stage_evidence",
            "node_id": "search-1",
            "evidence_id": str(evidence_id),
            "tool": "document_search",
            "query": "izin devri",
        }
    ]


@pytest.mark.asyncio
async def test_report_stage_evidence_without_a_stream_records_nothing(monkeypatch):
    from agents.graphs import stage_report

    recorder = _FakeRecorder()
    monkeypatch.setattr(stage_report, "_stream_writer", lambda: None)

    assert await stage_report.report_stage_evidence("search-1", _evidence(), recorder=recorder) is False
    assert recorder.recorded == []


@pytest.mark.asyncio
async def test_report_stage_evidence_reports_failure_when_nothing_was_recorded(monkeypatch):
    from agents.graphs import stage_report

    events = []
    monkeypatch.setattr(stage_report, "_stream_writer", lambda: events.append)

    reported = await stage_report.report_stage_evidence("search-1", _evidence(), recorder=_FakeRecorder(None))

    assert reported is False
    assert events == []
