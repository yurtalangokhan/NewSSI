"""A reloaded FlowAgent run replays which published flow version it ran.

AgentsRoute persists ``thread_metadata["flow_versions"][<trailing AI id>]``
after a FlowAgent run. On reload the reconstruction must re-emit that as a
``flow_version`` packet on the run's turn, so the chat-side flow strip pins
to the version that actually ran instead of the currently published one.
"""

from langchain_core.messages import AIMessage, HumanMessage

from service.ChatHistoryReconstruction import (
    reconstruct_message_tree,
    reconstruct_messages,
)
from tests.service.test_chat_history_reconstruction_flow_timeline import (
    _BLOB,
    _FINAL_AI_ID,
    _flow_run_checkpoints,
)


def _flow_version_packets(packets_2d):
    return [p for turn in packets_2d for p in turn if p["obj"].get("type") == "flow_version"]


def test_linear_reload_replays_the_pinned_flow_version():
    messages, packets_2d = reconstruct_messages(
        [HumanMessage(content="soru", id="h1"), AIMessage(content="cevap", id="ai-1")],
        thread_metadata={"flow_versions": {"ai-1": 4}},
        chat_session_id="s1",
    )

    versions = _flow_version_packets(packets_2d)
    assert len(versions) == 1
    assert versions[0]["obj"]["version_no"] == 4
    assert packets_2d[-1][0]["obj"]["type"] == "flow_version"


def test_blob_backed_reload_replays_the_pinned_flow_version():
    _messages, packets_2d = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={
            "flow_timelines": {_FINAL_AI_ID: _BLOB},
            "flow_versions": {_FINAL_AI_ID: 9},
        },
        chat_session_id="s1",
    )

    versions = _flow_version_packets(packets_2d)
    assert [v["obj"]["version_no"] for v in versions] == [9]


def test_reload_without_flow_versions_emits_no_flow_version_packet():
    _messages, packets_2d = reconstruct_messages(
        [HumanMessage(content="soru", id="h1"), AIMessage(content="cevap", id="ai-1")],
        thread_metadata={},
        chat_session_id="s1",
    )
    assert _flow_version_packets(packets_2d) == []
