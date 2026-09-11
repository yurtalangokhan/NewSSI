"""_LiveStageTracker — per-stage bookkeeping for a FlowAgent SSE run."""

from api.routes.flow_stage_tracker import _LiveStageTracker


def _t(final=None):
    return _LiveStageTracker(set(final or []), label_fn=lambda nid: nid.split("-")[0])


def test_order_and_iteration_counters():
    t = _t()
    s1 = t.begin_stage("A-1", 1000)
    assert (s1.order, s1.iteration, s1.key) == (1, 1, "A-1#1")
    t.end_stage("A-1", 1500)
    s2 = t.begin_stage("B-1", 1600)
    assert (s2.order, s2.iteration) == (2, 1)
    t.end_stage("B-1", 1700)
    s3 = t.begin_stage("A-1", 1800)  # loop re-entry
    assert (s3.order, s3.iteration, s3.key) == (3, 2, "A-1#2")


def test_known_nonfinal_uses_final_node_ids():
    t = _t(final={"OUT-1"})
    t.begin_stage("MID-1", 0)
    assert t.current_is_known_nonfinal() is True
    t.end_stage("MID-1", 1)
    t.begin_stage("OUT-1", 2)
    assert t.current_is_known_nonfinal() is False


def test_label_fn_applied():
    t = _LiveStageTracker(
        set(),
        label_fn=lambda nid: "Analiz Ajanı" if nid.startswith("ReActAgent") else nid,
    )
    s = t.begin_stage("ReActAgent-abc123", 0)
    assert s.label == "Analiz Ajanı"


def test_build_blob_shape_and_final_flag():
    t = _t(final={"OUT-1"})
    t.begin_stage("MID-1", 1000)
    t.add_reasoning("thinking")
    t.add_output("prep result")
    t.end_stage("MID-1", 1200)
    t.begin_stage("OUT-1", 1300)
    t.add_output("the answer")
    t.end_stage("OUT-1", 1500)
    blob = t.build_blob(final_stage_key="OUT-1#1")
    assert [s["stage_key"] for s in blob["stages"]] == ["MID-1#1", "OUT-1#1"]
    assert [s["is_final"] for s in blob["stages"]] == [False, True]
    assert blob["stages"][0]["reasoning_text"] == "thinking"
    assert blob["stages"][0]["output_text"] == "prep result"
    assert blob["stages"][0]["order"] == 1
    assert blob["stages"][0]["started_at"] == 1000
    assert blob["stages"][0]["ended_at"] == 1200
    assert blob["final_stage_key"] == "OUT-1#1"
    assert blob["truncated"] is False


def test_build_blob_records_tools():
    t = _t()
    t.begin_stage("MID-1", 0)
    t.add_tool("web_search", "c1", {"q": "x"}, 10)
    t.add_tool_result("c1", "hits", 20)
    t.end_stage("MID-1", 30)
    tool = t.build_blob(None)["stages"][0]["tools"][0]
    assert tool["tool_name"] == "web_search"
    assert tool["call_id"] == "c1"
    assert tool["args"] == {"q": "x"}
    assert tool["result_preview"] == "hits"
    assert tool["started_at"] == 10 and tool["ended_at"] == 20


def test_build_blob_truncates_large_output():
    t = _t()
    t.begin_stage("MID-1", 0)
    t.add_output("x" * 20_000)
    t.end_stage("MID-1", 1)
    blob = t.build_blob(None)
    assert len(blob["stages"][0]["output_text"].encode()) <= 8 * 1024
    assert blob["truncated"] is True


def test_build_blob_truncates_large_tool_preview():
    t = _t()
    t.begin_stage("MID-1", 0)
    t.add_tool("run_python", "c", {}, 1)
    t.add_tool_result("c", "y" * 5000, 2)
    t.end_stage("MID-1", 3)
    blob = t.build_blob(None)
    assert len(blob["stages"][0]["tools"][0]["result_preview"].encode()) <= 2 * 1024
    assert blob["truncated"] is True


def test_build_blob_caps_stage_count():
    t = _t()
    for i in range(300):
        t.begin_stage(f"N-{i}", i)
        t.add_output("y")
        t.end_stage(f"N-{i}", i + 1)
    blob = t.build_blob(None)
    assert len(blob["stages"]) == 200
    assert blob["truncated"] is True


def test_resolve_final_stage_key_is_last_with_output():
    t = _t()
    t.begin_stage("A-1", 0)
    t.add_output("a")
    t.end_stage("A-1", 1)
    t.begin_stage("B-1", 2)
    t.end_stage("B-1", 3)  # tool-only, no output
    t.begin_stage("C-1", 4)
    t.add_output("c")
    t.end_stage("C-1", 5)
    assert t.resolve_final_stage_key() == "C-1#1"


def test_resolve_final_stage_key_none_when_no_output():
    t = _t()
    t.begin_stage("A-1", 0)
    t.end_stage("A-1", 1)
    assert t.resolve_final_stage_key() is None


def test_end_stage_marks_status_but_keeps_current():
    t = _t()
    t.begin_stage("A-1", 0)
    t.end_stage("A-1", 5, status="cancelled")
    # `current` is intentionally NOT cleared — a late reasoning/tool packet
    # for the just-ended stage still needs to attach to it.
    assert t.current is not None and t.current.node_id == "A-1"
    assert t.stage_open is False
    assert t.build_blob(None)["stages"][0]["status"] == "cancelled"


def test_late_content_after_end_still_attaches_to_the_stage():
    t = _t()
    t.begin_stage("A-1", 0)
    t.end_stage("A-1", 5)
    t.add_reasoning("trailing thought")  # arrives after task_result
    assert t.build_blob(None)["stages"][0]["reasoning_text"] == "trailing thought"


def test_add_content_without_open_stage_is_ignored():
    t = _t()
    t.add_reasoning("orphan")
    t.add_output("orphan")
    assert t.build_blob(None)["stages"] == []


def test_build_blob_deduplicates_reasoning_within_and_across_stages():
    t = _t()
    t.begin_stage("S1", 0)
    t.add_reasoning("Common thought")
    t.begin_reasoning()
    t.add_reasoning("Common thought")  # duplicate within S1
    t.end_stage("S1", 10)

    t.begin_stage("S2", 11)
    t.add_reasoning("Common thought")  # leaked into S2
    t.begin_reasoning()
    t.add_reasoning("S2 specific thought")
    t.end_stage("S2", 20)

    blob = t.build_blob("S2#1")
    stages = blob["stages"]

    # S1 should have only 1 step and its reasoning_text should be 'Common thought'
    assert len(stages[0]["steps"]) == 1
    assert stages[0]["steps"][0]["text"] == "Common thought"
    assert stages[0]["reasoning_text"] == "Common thought"

    # S2 should filter 'Common thought' and keep only 'S2 specific thought'
    assert len(stages[1]["steps"]) == 1
    assert stages[1]["steps"][0]["text"] == "S2 specific thought"
    assert stages[1]["reasoning_text"] == "S2 specific thought"
