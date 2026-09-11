"""Blob-backed FlowAgent runs rebuild from flow_timelines on reload."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.ChatHistoryReconstruction import reconstruct_message_tree

_FINAL_AI_ID = "run-ai-final"

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
            "tools": [],
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
            "output_text": "FINAL",
            "tools": [],
        },
    ],
    "final_stage_key": "A-1#1",
    "truncated": False,
}


def _flow_run_checkpoints():
    """Human -> research stage (own checkpoint) -> answer stage checkpoint
    whose delta carries the trailing AI id that keys the blob."""
    human = HumanMessage(content="soru", id="h1")
    research = AIMessage(content="prep text", id="stage-research")
    final = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    return [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "c1",
            "parent_checkpoint_id": "c0",
            "messages": [human, research],
        },
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human, research, final],
        },
    ]


def test_blob_backed_run_folds_intermediate_into_timeline():
    messages, packets_2d = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assistant = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["message"] == "FINAL"

    turn = packets_2d[-1]
    types = [p["obj"]["type"] for p in turn]
    assert "flow_stage_start" in types
    assert "flow_stage_output_delta" in types  # the folded "prep" text
    assert types[-2:] == ["message_start", "stop"]

    ms = next(p for p in turn if p["obj"]["type"] == "message_start")
    assert ms["obj"]["content"] == "FINAL"
    # "prep" is in the timeline, never the bubble
    folded = "".join(
        p["obj"].get("content", "") for p in turn if p["obj"]["type"] == "flow_stage_output_delta"
    )
    assert folded == "prep"
    # every stage gets a flow_stage_start bracket; only the non-final one folds
    starts = [p["obj"] for p in turn if p["obj"]["type"] == "flow_stage_start"]
    assert {s["stage_key"] for s in starts} == {"R-1#1", "A-1#1"}
    assert {s["stage_key"]: s["is_final_stage"] for s in starts} == {
        "R-1#1": False,
        "A-1#1": True,
    }


def test_blob_backed_run_reports_thinking_duration_from_stage_span():
    """A reloaded FlowAgent run shows the same "thought for X" number it showed
    live, not the "thought for a while" fallback. The blob has no run-level
    clock, so it comes from the stage span: first started_at 1000 -> last
    ended_at 1500 == 0.5s, floored up to the live path's 1s minimum."""
    messages, packets_2d = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assistant = next(m for m in messages if m["message_type"] == "assistant")
    assert assistant["processing_duration_seconds"] == 1

    turn = packets_2d[-1]
    ms = next(p for p in turn if p["obj"]["type"] == "message_start")
    assert ms["obj"]["pre_answer_processing_seconds"] == 1


def test_blob_backed_run_prefers_persisted_thinking_duration():
    """When the trailing AI message kept the exact live number in
    additional_kwargs, that wins over the stage-span estimate."""
    human = HumanMessage(content="soru", id="h1")
    research = AIMessage(content="prep text", id="stage-research")
    final = AIMessage(
        content="FINAL",
        id=_FINAL_AI_ID,
        additional_kwargs={"processing_duration_seconds": 42},
    )
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": [human, research]},
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human, research, final],
        },
    ]
    messages, packets_2d = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assistant = next(m for m in messages if m["message_type"] == "assistant")
    assert assistant["processing_duration_seconds"] == 42
    ms = next(p for p in packets_2d[-1] if p["obj"]["type"] == "message_start")
    assert ms["obj"]["pre_answer_processing_seconds"] == 42


def test_legacy_run_without_blob_is_untouched():
    """No flow_timelines -> the two AI messages reconstruct the old way
    (two assistant turns), no flow_stage_* packets."""
    messages, packets_2d = reconstruct_message_tree(
        _flow_run_checkpoints(),
        thread_metadata={},
        chat_session_id="s1",
    )
    assert [m["message_type"] for m in messages] == ["user", "assistant", "assistant"]
    all_types = [p["obj"]["type"] for turn in packets_2d for p in turn]
    assert "flow_stage_start" not in all_types


def test_forked_run_skips_blob_replay():
    """A mid-run branch fork leaves the run unclassified -> legacy path,
    no crash, no blob replay."""
    human = HumanMessage(content="soru", id="h1")
    research = AIMessage(content="prep text", id="stage-research")
    final_a = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    final_b = AIMessage(content="OTHER", id="run-ai-other")
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "c1",
            "parent_checkpoint_id": "c0",
            "messages": [human, research],
        },
        # c1 forks: two children each add a different trailing AI message
        {
            "checkpoint_id": "c2a",
            "parent_checkpoint_id": "c1",
            "messages": [human, research, final_a],
        },
        {
            "checkpoint_id": "c2b",
            "parent_checkpoint_id": "c1",
            "messages": [human, research, final_b],
        },
    ]
    messages, packets_2d = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )
    all_types = [p["obj"]["type"] for turn in packets_2d for p in turn]
    assert "flow_stage_start" not in all_types  # fork -> legacy, blob not replayed
    assert any(m["message"] == "FINAL" for m in messages)
    assert any(m["message"] == "OTHER" for m in messages)


def test_single_stage_flow_blob_still_yields_one_normal_turn():
    human = HumanMessage(content="q", id="h1")
    final = AIMessage(content="ONLY", id=_FINAL_AI_ID)
    blob = {
        "stages": [
            {
                "stage_key": "S#1",
                "node_id": "S",
                "label": "Solo",
                "order": 1,
                "iteration": 1,
                "started_at": 0,
                "ended_at": 10,
                "status": "done",
                "is_final": True,
                "reasoning_text": "",
                "output_text": "ONLY",
                "tools": [],
            }
        ],
        "final_stage_key": "S#1",
        "truncated": False,
    }
    messages, packets_2d = reconstruct_message_tree(
        [
            {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
            {
                "checkpoint_id": "c1",
                "parent_checkpoint_id": "c0",
                "messages": [human, final],
            },
        ],
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: blob}},
        chat_session_id="s1",
    )
    assistant = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["message"] == "ONLY"
    types = [p["obj"]["type"] for p in packets_2d[-1]]
    # single final stage: its bracket + the answer bubble, no folded output
    assert types[-2:] == ["message_start", "stop"]
    assert "flow_stage_output_delta" not in types
    start = next(p for p in packets_2d[-1] if p["obj"]["type"] == "flow_stage_start")
    assert start["obj"]["is_final_stage"] is True


def test_conditional_router_loop_chain_is_still_blob_backed():
    """A ConditionalRouter/Loop makes the run's message chain longer (several
    AI messages across sequential checkpoints) but never branched — the blob
    path must still handle it, not fall back to the legacy parallel-tab view."""
    human = HumanMessage(content="soru", id="h1")
    a1 = AIMessage(content="station 1 draft <<TASLAK_TAMAM>>", id="ai-1")
    a2 = AIMessage(content="station 2 draft <<TASLAK_TAMAM>>", id="ai-2")
    a3 = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": [human, a1]},
        {"checkpoint_id": "c2", "parent_checkpoint_id": "c1", "messages": [human, a1, a2]},
        {"checkpoint_id": "c3", "parent_checkpoint_id": "c2", "messages": [human, a1, a2, a3]},
        # a bare __end__ checkpoint hanging off the terminal must NOT disqualify it
        {"checkpoint_id": "c4", "parent_checkpoint_id": "c3", "messages": [human, a1, a2, a3]},
    ]
    messages, packets_2d = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )
    all_types = [p["obj"]["type"] for turn in packets_2d for p in turn]
    assert "flow_stage_start" in all_types  # blob replayed, not legacy
    assistant = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["message"] == "FINAL"


def _prompt_template_run_checkpoints():
    """ChatInput -> SetVariable -> PromptTemplate -> agent.

    Since Phase 1 the Prompt Template emits its rendered text as a message so
    it can feed the agent. That message is a HumanMessage, so on reload it
    rendered as a SECOND user bubble containing the internal prompt. The real
    user turn is the one AgentHelpers stamped with ``persona_id``.
    """
    user = HumanMessage(content="Kargom gecikti", id="h1", additional_kwargs={"persona_id": 7})
    rendered = HumanMessage(content="Şu mesaja yanıt ver: Kargom gecikti", id="pt-msg")
    final = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    return [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [user]},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": [user, rendered]},
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [user, rendered, final],
        },
    ]


def test_prompt_template_message_is_not_a_second_user_bubble():
    messages, _ = reconstruct_message_tree(
        _prompt_template_run_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    user_bubbles = [m for m in messages if m["message_type"] == "user"]
    assert [m["message"] for m in user_bubbles] == ["Kargom gecikti"]


def test_a_legacy_unstamped_user_message_still_opens_a_turn():
    """Threads predating persona_id stamping have no marker on the user's own
    message — those must keep rendering. Only a *second* unstamped human
    message inside an already-open turn is flow-internal."""
    user = HumanMessage(content="eski soru", id="h1")
    final = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    checkpoints = [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [user]},
        {"checkpoint_id": "c1", "parent_checkpoint_id": "c0", "messages": [user, final]},
    ]

    messages, _ = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assert [m["message"] for m in messages if m["message_type"] == "user"] == ["eski soru"]


_DOC_PAYLOAD = (
    '{"__generated_file__": true, "file_id": "f-13b5", '
    '"filename": "fikirler.pdf", "mime_type": "application/pdf", '
    '"size_bytes": 4096, "download_url": "/api/files/f-13b5"}'
)


def _flow_run_with_document_checkpoints():
    """Same run, but the research stage called a document tool. The blob keeps
    only a truncated `result_preview` of that ToolMessage, so the file card can
    be rebuilt from the checkpoint alone."""
    human = HumanMessage(content="soru", id="h1")
    call = AIMessage(
        content="",
        id="stage-research",
        tool_calls=[{"name": "create_document", "args": {}, "id": "tc-1", "type": "tool_call"}],
    )
    result = ToolMessage(content=_DOC_PAYLOAD, name="create_document", tool_call_id="tc-1")
    final = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    return [
        {"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [human]},
        {
            "checkpoint_id": "c1",
            "parent_checkpoint_id": "c0",
            "messages": [human, call, result],
        },
        {
            "checkpoint_id": "c2",
            "parent_checkpoint_id": "c1",
            "messages": [human, call, result, final],
        },
    ]


def test_blob_backed_run_keeps_a_generated_file_card():
    """A document produced inside a flow stage survives a reload.

    The blob only carries a truncated preview of the document tool's JSON, so
    folding the ToolMessage away with the rest of the run's narration used to
    lose the file entirely — the card was there live and gone after F5.
    """
    messages, packets_2d = reconstruct_message_tree(
        _flow_run_with_document_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    turn = packets_2d[-1]
    files = [p for p in turn if p["obj"]["type"] == "generated_file"]
    assert len(files) == 1
    assert files[0]["obj"]["file_id"] == "f-13b5"
    assert files[0]["obj"]["filename"] == "fikirler.pdf"

    # Its own display group, ahead of the answer bubble — sharing a turn with
    # the answer would let the chat renderer win and hide the card.
    answer = next(p for p in turn if p["obj"]["type"] == "message_start")
    file_turn = files[0]["placement"]["turn_index"]
    assert file_turn < answer["placement"]["turn_index"]
    assert all(
        p["placement"]["turn_index"] != file_turn
        for p in turn
        if p["obj"]["type"] not in ("generated_file",)
    )

    # The run still rebuilds normally around it.
    assistant = [m for m in messages if m["message_type"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["message"] == "FINAL"
    assert [p["obj"]["type"] for p in turn][-2:] == ["message_start", "stop"]


_FOREACH_USER_TEXT = "satır bir\nsatır iki\nsatır üç"


def _foreach_run_checkpoints(*, stamped: bool = True, with_final: bool = True):
    """ChatInput -> Loop(foreach) -> summarizer -> back to Loop -> organizer.

    The foreach Loop places each item in ``messages`` as a HumanMessage so the
    body agent consumes it (flow_builder._make_foreach_node), and emits the
    joined results the same way on the ``done`` branch. Only the first of those
    lands while the user's turn is still open — every later one arrives after
    the body already answered.
    """
    kwargs = {"additional_kwargs": {"persona_id": 7}} if stamped else {}
    user = HumanMessage(content=_FOREACH_USER_TEXT, id="h1", **kwargs)
    msgs = [user]
    checkpoints = [{"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": list(msgs)}]
    prev = "c0"
    for i in (1, 2, 3):
        msgs = [*msgs, HumanMessage(content=f"satır {i}", id=f"item-{i}")]
        checkpoints.append(
            {"checkpoint_id": f"i{i}", "parent_checkpoint_id": prev, "messages": list(msgs)}
        )
        msgs = [*msgs, AIMessage(content=f"özet {i}", id=f"sum-{i}")]
        checkpoints.append(
            {"checkpoint_id": f"a{i}", "parent_checkpoint_id": f"i{i}", "messages": list(msgs)}
        )
        prev = f"a{i}"
    if with_final:
        msgs = [*msgs, HumanMessage(content="özet 1\nözet 2\nözet 3", id="joined")]
        checkpoints.append(
            {"checkpoint_id": "done", "parent_checkpoint_id": prev, "messages": list(msgs)}
        )
        msgs = [*msgs, AIMessage(content="FINAL", id=_FINAL_AI_ID)]
        checkpoints.append(
            {"checkpoint_id": "fin", "parent_checkpoint_id": "done", "messages": list(msgs)}
        )
    return checkpoints


def test_foreach_loop_items_are_not_user_bubbles():
    """A Loop over N items must not put N-1 fake user bubbles in the chat.

    `_is_flow_internal_human` only suppressed an unstamped human message while
    a user turn was still open, and the body's first answer closes that turn —
    so item 1 was hidden and items 2..N leaked as messages the user never sent.
    """
    messages, _ = reconstruct_message_tree(
        _foreach_run_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assert [m["message"] for m in messages if m["message_type"] == "user"] == [_FOREACH_USER_TEXT]


def test_foreach_loop_run_stays_one_turn():
    """The same leak split one run into N turns: `_delta_starts_new_run` treats
    any human message as a run boundary, so the fold/blob walk stopped at the
    last loop item and every iteration drew its own stage strip and answer."""
    messages, packets_2d = reconstruct_message_tree(
        _foreach_run_checkpoints(),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assistant = [m for m in messages if m["message_type"] == "assistant"]
    assert [m["message"] for m in assistant] == ["FINAL"]
    # Exactly one assistant turn (packets_2d holds only those) — three loop
    # iterations used to draw three, each with its own stage strip.
    assert len(packets_2d) == 1
    # The per-item summaries live in the timeline, never as their own bubbles.
    assert "flow_stage_start" in [p["obj"]["type"] for p in packets_2d[-1]]


def test_foreach_loop_items_hidden_without_a_blob():
    """A cancelled/legacy run has no flow_timelines blob, but the fake user
    bubbles came from the message stream, not the blob — they must go too."""
    messages, _ = reconstruct_message_tree(
        _foreach_run_checkpoints(with_final=False),
        thread_metadata={},
        chat_session_id="s1",
    )

    assert [m["message"] for m in messages if m["message_type"] == "user"] == [_FOREACH_USER_TEXT]


def test_unstamped_thread_keeps_every_human_message():
    """Threads predating persona_id stamping carry no marker anywhere, so an
    unstamped human message is all we ever see — those must keep rendering as
    real turns rather than being swallowed as flow-internal."""
    messages, _ = reconstruct_message_tree(
        _foreach_run_checkpoints(stamped=False),
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    user_texts = [m["message"] for m in messages if m["message_type"] == "user"]
    assert user_texts[0] == _FOREACH_USER_TEXT
    assert len(user_texts) > 1


def test_thread_straddling_the_stamping_change_keeps_its_old_user_turns():
    """A thread that started before AgentHelpers stamped ``persona_id`` and
    continued after it must not lose its older user turns: the stamp only
    becomes evidence once one has actually been seen."""
    old_user = HumanMessage(content="eski soru", id="h0")
    old_answer = AIMessage(content="eski cevap", id="a0")
    new_user = HumanMessage(content="yeni soru", id="h1", additional_kwargs={"persona_id": 7})
    rendered = HumanMessage(content="dahili prompt", id="pt-msg")
    final = AIMessage(content="FINAL", id=_FINAL_AI_ID)
    msgs = [old_user]
    checkpoints = [{"checkpoint_id": "c0", "parent_checkpoint_id": None, "messages": [old_user]}]
    for cid, parent, nxt in (
        ("c1", "c0", old_answer),
        ("c2", "c1", new_user),
        ("c3", "c2", rendered),
        ("c4", "c3", final),
    ):
        msgs = [*msgs, nxt]
        checkpoints.append(
            {"checkpoint_id": cid, "parent_checkpoint_id": parent, "messages": list(msgs)}
        )

    messages, _ = reconstruct_message_tree(
        checkpoints,
        thread_metadata={"flow_timelines": {_FINAL_AI_ID: _BLOB}},
        chat_session_id="s1",
    )

    assert [m["message"] for m in messages if m["message_type"] == "user"] == [
        "eski soru",
        "yeni soru",
    ]
