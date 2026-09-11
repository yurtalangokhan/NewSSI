"""The three processing nodes: Data Operations, Split Text, Type Convert.

The operation semantics themselves are covered by the pure tests in
`tests/domain/flows/test_data_ops_*.py`. What is tested here is the plumbing:
which input a node reads, where the result lands, and what leaves as a
message.
"""

from __future__ import annotations

import pandas as pd
import pytest
from langchain_core.messages import HumanMessage

from agents.graphs.flow_builder import (
    _make_operations_node,
    _make_split_text_node,
    _make_type_converter_node,
)
from core.exceptions import FlowBuildError
from models.flows import FlowNode


def _node(node_type, node_id="op-1", **values) -> FlowNode:
    return FlowNode(id=node_id, type=node_type, values=values)


async def _run(fn, messages=None, scratch=None):
    state = {
        "messages": messages if messages is not None else [HumanMessage(content="")],
        "scratch": scratch or {},
    }
    return await fn(state, None)


# ---------------------------------------------------------------------------
# Data Operations — input routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_text_operation_reads_the_text_field():
    fn = _make_operations_node(
        _node(
            "Operations", operation="Case Conversion", text_input="Merhaba", case_type="uppercase"
        )
    )
    result = await _run(fn)
    assert result["scratch"]["op-1"] == "MERHABA"


@pytest.mark.asyncio
async def test_a_wired_text_port_beats_the_text_field():
    fn = _make_operations_node(
        _node("Operations", operation="Case Conversion", text_input="alan", case_type="uppercase"),
        port_sources={"text_input": "up-1"},
    )
    result = await _run(fn, scratch={"up-1": "porttan"})
    assert result["scratch"]["op-1"] == "PORTTAN"


@pytest.mark.asyncio
async def test_a_json_operation_reads_the_wired_data_port():
    fn = _make_operations_node(
        _node("Operations", operation="Select Keys", select_keys_input=["a"]),
        port_sources={"data": "up-1"},
    )
    result = await _run(fn, scratch={"up-1": {"a": 1, "b": 2}})
    assert result["scratch"]["op-1"] == {"a": 1}


@pytest.mark.asyncio
async def test_a_table_operation_reads_the_wired_table_port():
    fn = _make_operations_node(
        _node("Operations", operation="Head", num_rows=1),
        port_sources={"df": "up-1"},
    )
    result = await _run(fn, scratch={"up-1": pd.DataFrame({"a": [1, 2, 3]})})
    assert list(result["scratch"]["op-1"]["a"]) == [1]


@pytest.mark.asyncio
async def test_merge_reads_its_two_dedicated_ports():
    fn = _make_operations_node(
        _node("Operations", operation="Merge", merge_on_column="id", merge_how="inner"),
        port_sources={"left_dataframe": "l", "right_dataframe": "r"},
    )
    result = await _run(
        fn,
        scratch={
            "l": pd.DataFrame({"id": [1], "ad": ["ali"]}),
            "r": pd.DataFrame({"id": [1], "puan": [10]}),
        },
    )
    assert sorted(result["scratch"]["op-1"].columns) == ["ad", "id", "puan"]


@pytest.mark.asyncio
async def test_concatenate_takes_every_wired_table():
    fn = _make_operations_node(
        _node("Operations", operation="Concatenate"),
        port_sources={"df": "a"},
        extra_frame_sources=["b"],
    )
    result = await _run(fn, scratch={"a": pd.DataFrame({"x": [1]}), "b": pd.DataFrame({"x": [2]})})
    assert list(result["scratch"]["op-1"]["x"]) == [1, 2]


# ---------------------------------------------------------------------------
# Data Operations — output routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_text_operation_falls_back_to_the_latest_message():
    """The flow's message arrives on `input`, not on `text_input`. Without this
    fallback a Text operation silently works on an empty string."""
    fn = _make_operations_node(
        _node("Operations", operation="Case Conversion", case_type="uppercase")
    )
    result = await _run(fn, messages=[HumanMessage(content="akistan")])
    assert result["scratch"]["op-1"] == "AKISTAN"


@pytest.mark.asyncio
async def test_the_text_field_still_wins_over_the_latest_message():
    fn = _make_operations_node(
        _node("Operations", operation="Case Conversion", text_input="alan", case_type="uppercase")
    )
    result = await _run(fn, messages=[HumanMessage(content="mesaj")])
    assert result["scratch"]["op-1"] == "ALAN"


@pytest.mark.asyncio
async def test_word_count_is_a_text_operation_that_yields_json():
    fn = _make_operations_node(
        _node(
            "Operations",
            operation="Word Count",
            text_input="bir iki",
            count_words=True,
            count_characters=False,
            count_lines=False,
        )
    )
    result = await _run(fn)
    assert result["scratch"]["op-1"]["word_count"] == 2


@pytest.mark.asyncio
async def test_text_to_dataframe_is_a_text_operation_that_yields_a_table():
    fn = _make_operations_node(
        _node(
            "Operations",
            operation="Text to DataFrame",
            text_input="| ad |\n| ali |",
            table_separator="|",
            has_header=True,
        )
    )
    result = await _run(fn)
    assert list(result["scratch"]["op-1"]["ad"]) == ["ali"]


@pytest.mark.asyncio
async def test_the_result_also_leaves_as_a_readable_message():
    fn = _make_operations_node(
        _node(
            "Operations",
            operation="Text Extract",
            text_input="a1b2",
            extract_pattern=r"\d",
            max_matches=0,
        )
    )
    result = await _run(fn)
    # A list result renders one item per line, as Langflow does.
    assert result["messages"][-1].content == "1\n2"


@pytest.mark.asyncio
async def test_an_empty_text_operation_stores_nothing_rather_than_none():
    """Langflow's text guard returns None for empty input; the node must not
    write that into scratch as a value a downstream node would read."""
    fn = _make_operations_node(
        _node("Operations", operation="Case Conversion", text_input="", case_type="uppercase")
    )
    result = await _run(fn, messages=[])
    assert result["scratch"]["op-1"] == ""


@pytest.mark.asyncio
async def test_an_unknown_operation_fails_the_build():
    with pytest.raises(FlowBuildError, match="operation"):
        _make_operations_node(_node("Operations", operation="Yok Böyle"))


@pytest.mark.asyncio
async def test_an_operation_must_be_chosen():
    with pytest.raises(FlowBuildError, match="operation"):
        _make_operations_node(_node("Operations"))


# ---------------------------------------------------------------------------
# Split Text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_split_text_chunks_the_latest_message_by_default():
    fn = _make_split_text_node(
        _node("SplitText", "split-1", chunk_size=4, chunk_overlap=0, separator="\n")
    )
    result = await _run(fn, messages=[HumanMessage(content="bir\niki")])
    assert list(result["scratch"]["split-1"]["text"]) == ["bir", "iki"]


@pytest.mark.asyncio
async def test_split_text_prefers_a_wired_input():
    fn = _make_split_text_node(
        _node("SplitText", "split-1", chunk_size=4, chunk_overlap=0, separator="\n"),
        port_sources={"data_inputs": "up-1"},
    )
    result = await _run(fn, messages=[HumanMessage(content="yoksay")], scratch={"up-1": "bir\niki"})
    assert list(result["scratch"]["split-1"]["text"]) == ["bir", "iki"]


@pytest.mark.asyncio
async def test_split_text_reports_an_empty_input_clearly():
    fn = _make_split_text_node(_node("SplitText", "split-1", chunk_size=10, chunk_overlap=0))
    with pytest.raises(FlowBuildError, match="Split Text"):
        await _run(fn, messages=[])


# ---------------------------------------------------------------------------
# Type Convert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_type_convert_turns_the_message_into_json():
    fn = _make_type_converter_node(_node("TypeConverter", "conv-1", output_type="JSON"))
    result = await _run(fn, messages=[HumanMessage(content="merhaba")])
    assert result["scratch"]["conv-1"] == {"text": "merhaba"}


@pytest.mark.asyncio
async def test_type_convert_reads_a_wired_input_over_the_message():
    fn = _make_type_converter_node(
        _node("TypeConverter", "conv-1", output_type="Table"),
        port_sources={"input_data": "up-1"},
    )
    result = await _run(fn, scratch={"up-1": {"records": [{"a": 1}, {"a": 2}]}})
    assert list(result["scratch"]["conv-1"]["a"]) == [1, 2]


@pytest.mark.asyncio
async def test_type_convert_auto_parse_reads_a_csv_message():
    fn = _make_type_converter_node(
        _node("TypeConverter", "conv-1", output_type="Table", auto_parse=True)
    )
    result = await _run(fn, messages=[HumanMessage(content="a,b\n1,2")])
    assert list(result["scratch"]["conv-1"].columns) == ["a", "b"]


@pytest.mark.asyncio
async def test_type_convert_rejects_an_unknown_output_type():
    fn = _make_type_converter_node(_node("TypeConverter", "conv-1", output_type="Yok"))
    with pytest.raises(FlowBuildError, match="output type"):
        await _run(fn, messages=[HumanMessage(content="x")])
