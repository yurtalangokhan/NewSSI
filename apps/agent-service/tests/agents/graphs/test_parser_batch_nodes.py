"""Parser and Batch Run — the two current Langflow components Phase 6 missed.

`Parser` renders structured data through a template; `Batch Run` runs a model
once per table row. Both bodies are ported from Langflow's own, so the
expectations below are about its behaviour, not a paraphrase of the name.
"""

from __future__ import annotations

import pandas as pd
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.graphs.flow_builder import _make_batch_run_node, _make_parser_node
from core.exceptions import FlowBuildError
from models.flows import FlowNode


@pytest.fixture(autouse=True)
def _fake_model_env(monkeypatch):
    monkeypatch.setenv("USE_FAKE_MODEL", "true")


ROWS = pd.DataFrame({"ad": ["ali", "veli"], "puan": [10, 20]})


async def _run(fn, scratch=None, messages=None):
    return await fn(
        {
            "messages": messages if messages is not None else [HumanMessage(content="")],
            "scratch": scratch or {},
        },
        None,
    )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parser_renders_a_wired_table_through_the_template():
    fn = _make_parser_node(
        FlowNode(
            id="p-1",
            type="Parser",
            values={"mode": "Parser", "pattern": "{ad}: {puan}", "sep": "\n"},
        ),
        port_sources={"input_data": "up"},
    )
    result = await _run(fn, scratch={"up": ROWS})
    assert result["scratch"]["p-1"] == "ali: 10\nveli: 20"


@pytest.mark.asyncio
async def test_parser_stringify_mode_ignores_the_template():
    fn = _make_parser_node(
        FlowNode(
            id="p-1", type="Parser", values={"mode": "Stringify", "pattern": "{ad}", "sep": "\n"}
        ),
        port_sources={"input_data": "up"},
    )
    result = await _run(fn, scratch={"up": {"ad": "ali"}})
    assert result["scratch"]["p-1"].startswith("```json")


@pytest.mark.asyncio
async def test_parser_falls_back_to_the_latest_message():
    fn = _make_parser_node(
        FlowNode(id="p-1", type="Parser", values={"mode": "Stringify", "pattern": "", "sep": "\n"})
    )
    result = await _run(fn, messages=[HumanMessage(content="duz metin")])
    assert result["scratch"]["p-1"] == "duz metin"


@pytest.mark.asyncio
async def test_parser_reports_a_bad_template_clearly():
    """A missing column over a table raises in Langflow too; the node turns it
    into an error naming the node instead of a bare KeyError."""
    fn = _make_parser_node(
        FlowNode(
            id="p-1", type="Parser", values={"mode": "Parser", "pattern": "{yok}", "sep": "\n"}
        ),
        port_sources={"input_data": "up"},
    )
    with pytest.raises(FlowBuildError, match="Parser"):
        await _run(fn, scratch={"up": ROWS})


@pytest.mark.asyncio
async def test_parsers_result_also_leaves_as_a_message():
    fn = _make_parser_node(
        FlowNode(
            id="p-1", type="Parser", values={"mode": "Parser", "pattern": "{ad}", "sep": ", "}
        ),
        port_sources={"input_data": "up"},
    )
    result = await _run(fn, scratch={"up": ROWS})
    assert result["messages"][-1].content == "ali, veli"


# ---------------------------------------------------------------------------
# Batch Run
# ---------------------------------------------------------------------------


class _BatchSpy:
    """Stands in for a chat model that supports `abatch`."""

    def __init__(self, replies=None):
        self.replies = replies
        self.conversations = None

    async def abatch(self, conversations):
        self.conversations = conversations
        replies = self.replies or [f"cevap-{i}" for i in range(len(conversations))]
        return [AIMessage(content=r) for r in replies]


def _batch_node(**values) -> FlowNode:
    base = {"column_name": "ad", "output_column_name": "model_response", "system_message": ""}
    base.update(values)
    return FlowNode(id="b-1", type="BatchRun", values=base)


@pytest.mark.asyncio
async def test_batch_run_adds_the_response_column_to_every_row():
    spy = _BatchSpy(["A", "B"])
    fn = _make_batch_run_node(_batch_node(), spy, port_sources={"df": "up"})
    out = await _run(fn, scratch={"up": ROWS})
    frame = out["scratch"]["b-1"]
    assert list(frame["model_response"]) == ["A", "B"]
    assert list(frame["ad"]) == ["ali", "veli"]


@pytest.mark.asyncio
async def test_batch_run_numbers_the_rows_so_order_is_recoverable():
    fn = _make_batch_run_node(_batch_node(), _BatchSpy(["A", "B"]), port_sources={"df": "up"})
    out = await _run(fn, scratch={"up": ROWS})
    assert list(out["scratch"]["b-1"]["batch_index"]) == [0, 1]


@pytest.mark.asyncio
async def test_batch_run_sends_one_conversation_per_row():
    spy = _BatchSpy(["A", "B"])
    fn = _make_batch_run_node(_batch_node(), spy, port_sources={"df": "up"})
    await _run(fn, scratch={"up": ROWS})
    assert [c[-1]["content"] for c in spy.conversations] == ["ali", "veli"]


@pytest.mark.asyncio
async def test_the_system_message_is_prepended_to_every_conversation():
    spy = _BatchSpy(["A", "B"])
    fn = _make_batch_run_node(
        _batch_node(system_message="Kisa cevapla"), spy, port_sources={"df": "up"}
    )
    await _run(fn, scratch={"up": ROWS})
    assert all(c[0] == {"role": "system", "content": "Kisa cevapla"} for c in spy.conversations)


@pytest.mark.asyncio
async def test_without_a_system_message_the_conversation_is_just_the_user_turn():
    spy = _BatchSpy(["A", "B"])
    fn = _make_batch_run_node(_batch_node(), spy, port_sources={"df": "up"})
    await _run(fn, scratch={"up": ROWS})
    assert all(len(c) == 1 for c in spy.conversations)


@pytest.mark.asyncio
async def test_a_blank_column_name_sends_the_whole_row():
    """Langflow formats the row as TOML when no column is chosen."""
    spy = _BatchSpy(["A", "B"])
    fn = _make_batch_run_node(_batch_node(column_name=""), spy, port_sources={"df": "up"})
    await _run(fn, scratch={"up": ROWS})
    assert "ali" in spy.conversations[0][-1]["content"]
    assert "puan" in spy.conversations[0][-1]["content"]


@pytest.mark.asyncio
async def test_a_column_that_is_not_there_is_reported():
    fn = _make_batch_run_node(
        _batch_node(column_name="yok"), _BatchSpy(), port_sources={"df": "up"}
    )
    with pytest.raises(FlowBuildError, match="not found"):
        await _run(fn, scratch={"up": ROWS})


@pytest.mark.asyncio
async def test_a_non_table_input_is_reported():
    fn = _make_batch_run_node(_batch_node(), _BatchSpy(), port_sources={"df": "up"})
    with pytest.raises(FlowBuildError, match="table"):
        await _run(fn, scratch={"up": "duz metin"})


@pytest.mark.asyncio
async def test_the_output_column_can_be_renamed():
    fn = _make_batch_run_node(
        _batch_node(output_column_name="ozet"), _BatchSpy(["A", "B"]), port_sources={"df": "up"}
    )
    out = await _run(fn, scratch={"up": ROWS})
    assert "ozet" in out["scratch"]["b-1"].columns
