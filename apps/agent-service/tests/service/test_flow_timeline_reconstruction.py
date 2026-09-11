from service.flow_timeline_reconstruction import emit_flow_timeline_packets

_BLOB = {
    "stages": [
        {
            "stage_key": "R-1#1",
            "node_id": "R-1",
            "label": "Araştırma",
            "order": 1,
            "iteration": 1,
            "started_at": 1000,
            "ended_at": 1200,
            "status": "done",
            "is_final": False,
            "reasoning_text": "düşün",
            "output_text": "prep",
            "tools": [
                {
                    "tool_name": "web_search",
                    "call_id": "c1",
                    "args": {"q": "x"},
                    "started_at": 1050,
                    "ended_at": 1100,
                    "result_preview": "hits",
                }
            ],
        },
        {
            "stage_key": "A-1#1",
            "node_id": "A-1",
            "label": "Analiz",
            "order": 2,
            "iteration": 1,
            "started_at": 1200,
            "ended_at": 1500,
            "status": "done",
            "is_final": True,
            "reasoning_text": "",
            "output_text": "final answer",
            "tools": [],
        },
    ],
    "final_stage_key": "A-1#1",
    "truncated": False,
}


def test_final_text_is_final_stage_output():
    _, final_text = emit_flow_timeline_packets(_BLOB)
    assert final_text == "final answer"


def test_every_stage_produces_a_bracket_final_flagged():
    packets, _ = emit_flow_timeline_packets(_BLOB)
    starts = [p for p in packets if p["obj"]["type"] == "flow_stage_start"]
    assert [p["obj"]["stage_key"] for p in starts] == ["R-1#1", "A-1#1"]
    assert [p["obj"]["is_final_stage"] for p in starts] == [False, True]
    # the final stage never emits a folded output delta
    final_keys = {
        p["placement"]["stage_key"]
        for p in packets
        if p["obj"]["type"] == "flow_stage_output_delta"
    }
    assert final_keys == {"R-1#1"}


def test_nonfinal_stage_packet_sequence_and_timestamps():
    packets, _ = emit_flow_timeline_packets(_BLOB)
    seq = [p["obj"]["type"] for p in packets if p["placement"]["stage_key"] == "R-1#1"]
    assert seq == [
        "flow_stage_start",
        "reasoning_start",
        "reasoning_delta",
        "flow_stage_output_delta",
        "custom_tool_start",
        "custom_tool_delta",
        "flow_stage_end",
    ]
    first = next(p for p in packets if p["placement"]["stage_key"] == "R-1#1")
    assert first["obj"]["timestamp"] == 1000
    assert first["placement"]["stage_order"] == 1
    assert first["placement"]["iteration"] == 1


def test_tool_packets_carry_their_parent_stage_node_id():
    packets, _ = emit_flow_timeline_packets(_BLOB)
    tool_packets = [
        p for p in packets if p["obj"]["type"] in ("custom_tool_start", "custom_tool_delta")
    ]
    assert tool_packets
    assert all(p["obj"]["stage_node_id"] == "R-1" for p in tool_packets)


def test_tool_only_nonfinal_stage_has_no_output_delta():
    blob = {
        "stages": [
            {
                "stage_key": "T-1#1",
                "node_id": "T-1",
                "label": "Tool",
                "order": 1,
                "iteration": 1,
                "started_at": 0,
                "ended_at": 5,
                "status": "done",
                "is_final": False,
                "reasoning_text": "",
                "output_text": "",
                "tools": [
                    {
                        "tool_name": "run_python",
                        "call_id": "c",
                        "args": {},
                        "started_at": 1,
                        "ended_at": 4,
                        "result_preview": "42",
                    }
                ],
            },
            {
                "stage_key": "F-1#1",
                "node_id": "F-1",
                "label": "Final",
                "order": 2,
                "iteration": 1,
                "started_at": 5,
                "ended_at": 9,
                "status": "done",
                "is_final": True,
                "reasoning_text": "",
                "output_text": "done",
                "tools": [],
            },
        ],
        "final_stage_key": "F-1#1",
        "truncated": False,
    }
    packets, final_text = emit_flow_timeline_packets(blob)
    assert "flow_stage_output_delta" not in [p["obj"]["type"] for p in packets]
    assert final_text == "done"


def test_missing_final_flag_returns_empty_final_text():
    blob = {
        "stages": [
            {
                "stage_key": "X-1#1",
                "node_id": "X-1",
                "label": "X",
                "order": 1,
                "iteration": 1,
                "started_at": 0,
                "ended_at": 1,
                "status": "cancelled",
                "is_final": False,
                "reasoning_text": "r",
                "output_text": "",
                "tools": [],
            }
        ],
        "final_stage_key": None,
        "truncated": False,
    }
    packets, final_text = emit_flow_timeline_packets(blob)
    assert final_text == ""
    assert packets[0]["obj"]["type"] == "flow_stage_start"
    assert packets[-1]["obj"]["status"] == "cancelled"


def test_empty_blob_is_safe():
    assert emit_flow_timeline_packets({}) == ([], "")
    assert emit_flow_timeline_packets({"stages": []}) == ([], "")


def test_deduplicate_reasoning_within_stage():
    blob = {
        "stages": [
            {
                "stage_key": "S1#1",
                "node_id": "S1",
                "label": "Stage 1",
                "order": 1,
                "iteration": 1,
                "is_final": False,
                "steps": [
                    {"kind": "reasoning", "text": "Analyzing data..."},
                    {"kind": "reasoning", "text": "Analyzing data..."},
                    {"kind": "output", "text": "Result 1"},
                ],
            }
        ]
    }
    packets, _ = emit_flow_timeline_packets(blob)
    deltas = [p["obj"]["reasoning"] for p in packets if p["obj"]["type"] == "reasoning_delta"]
    assert deltas == ["Analyzing data..."]


def test_strip_leaked_reasoning_from_prior_stages():
    blob = {
        "stages": [
            {
                "stage_key": "S1#1",
                "node_id": "S1",
                "label": "Stage 1",
                "order": 1,
                "iteration": 1,
                "is_final": False,
                "steps": [
                    {"kind": "reasoning", "text": "Researching topic..."},
                    {"kind": "output", "text": "Research done"},
                ],
            },
            {
                "stage_key": "S2#1",
                "node_id": "S2",
                "label": "Stage 2",
                "order": 2,
                "iteration": 1,
                "is_final": True,
                "steps": [
                    {"kind": "reasoning", "text": "Researching topic..."},  # leaked from S1
                    {"kind": "output", "text": "Final response"},
                ],
            },
        ]
    }
    packets, final_text = emit_flow_timeline_packets(blob)
    deltas = [p["obj"]["reasoning"] for p in packets if p["obj"]["type"] == "reasoning_delta"]
    # Should only appear once for Stage 1, not leaked into Stage 2
    assert deltas == ["Researching topic..."]
    s2_packets = [p for p in packets if p["placement"]["stage_key"] == "S2#1"]
    assert not any(p["obj"]["type"] == "reasoning_delta" for p in s2_packets)
