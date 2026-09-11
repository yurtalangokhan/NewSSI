from api.routes.flow_stage_labels import flow_stage_label


def test_prefers_user_label():
    nodes = {"ReActAgent-abc": {"type": "ReActAgent", "values": {"label": "Analiz Ajanı"}}}
    assert flow_stage_label("ReActAgent-abc", nodes) == "Analiz Ajanı"


def test_prettifies_type_when_no_label():
    nodes = {"ReActAgent-abc": {"type": "ReActAgent", "values": {}}}
    assert flow_stage_label("ReActAgent-abc", nodes) == "ReAct Agent"


def test_pipeline_stage_uses_its_stage_name_value():
    nodes = {"PipelineStage-1": {"type": "PipelineStage", "values": {"name": "Araştırma"}}}
    assert flow_stage_label("PipelineStage-1", nodes) == "Araştırma"


def test_label_value_still_wins_over_name():
    nodes = {
        "PipelineStage-1": {
            "type": "PipelineStage",
            "values": {"label": "Analiz", "name": "raw-name"},
        }
    }
    assert flow_stage_label("PipelineStage-1", nodes) == "Analiz"


def test_blank_name_falls_back_to_pretty_type():
    nodes = {"PipelineStage-1": {"type": "PipelineStage", "values": {"name": "  "}}}
    assert flow_stage_label("PipelineStage-1", nodes) == "Pipeline Stage"


def test_known_type_uses_explicit_pretty_name():
    nodes = {"cr-1": {"type": "ConditionalRouter", "values": {}}}
    assert flow_stage_label("cr-1", nodes) == "If-Else"


def test_falls_back_to_id_when_unknown():
    assert flow_stage_label("mystery-1", {}) == "mystery-1"


def test_blank_label_is_ignored():
    nodes = {"n": {"type": "ReActAgent", "values": {"label": "   "}}}
    assert flow_stage_label("n", nodes) == "ReAct Agent"


def test_set_variable_name_is_not_a_stage_label():
    """SetVariable's ``name`` is the *variable* name (Phase 0), not a canvas
    rename. Using it as the stage label puts a scratch key where a component
    name belongs — the timeline showed "musteri_mesaji" instead of
    "Set Variable"."""
    nodes = {"SetVariable-1": {"type": "SetVariable", "values": {"name": "musteri_mesaji"}}}
    assert flow_stage_label("SetVariable-1", nodes) == "Set Variable"


def test_set_variable_still_honours_an_explicit_canvas_rename():
    nodes = {
        "SetVariable-1": {
            "type": "SetVariable",
            "values": {"label": "Talebi sakla", "name": "musteri_mesaji"},
        }
    }
    assert flow_stage_label("SetVariable-1", nodes) == "Talebi sakla"
