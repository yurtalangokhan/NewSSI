"""`ask_user` geçmişte: cevaplanmış kart çiziliyor, cevapsız çağrı çizilmiyor.

Tasarımın en kırılgan yeri burası. İki ayrı kaynak aynı kartı üretebilir —
yeniden kurulum ve bekleyen interrupt — ve ikisi birden çizerse kullanıcı
aynı soruyu iki kez görür (E4).
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from service.ChatHistoryReconstruction import (
    reconstruct_message_tree,
    reconstruct_messages,
)

QUESTIONS = [
    {
        "question": "Raporu kim okuyacak?",
        "header": "Hedef kitle",
        "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
    }
]


def _call(call_id="c1", questions=QUESTIONS):
    return AIMessage(
        content="",
        tool_calls=[{"name": "ask_user", "args": {"questions": questions}, "id": call_id}],
    )


def _answer(call_id="c1", artifact=None, content="Hedef kitle: Yönetim"):
    return ToolMessage(
        content=content,
        name="ask_user",
        tool_call_id=call_id,
        artifact=artifact
        if artifact is not None
        else {
            "answered": True,
            "answers": {"Hedef kitle": ["Yönetim"]},
        },
    )


def _objs(messages):
    _, packets_2d = reconstruct_messages(messages, {}, "s1")
    return [p["obj"] for turn in packets_2d for p in turn if isinstance(p, dict)]


def _types(messages):
    return [o.get("type") for o in _objs(messages)]


def test_an_answered_question_comes_back_as_a_card_and_its_lock():
    objs = _objs(
        [
            HumanMessage(content="rapor hazırla"),
            _call(),
            _answer(),
            AIMessage(content="Hazırlıyorum."),
        ]
    )

    card = next(o for o in objs if o["type"] == "user_clarification")
    lock = next(o for o in objs if o["type"] == "user_clarification_answered")
    assert card["questions"][0]["header"] == "Hedef kitle"
    assert card["request_id"] == lock["request_id"] == "c1"
    assert lock["answers"] == {"Hedef kitle": ["Yönetim"]}


def test_the_generic_tool_card_is_never_drawn_for_it():
    """Ham JSON'lu araç kartı kullanıcıya hiçbir zaman gösterilmiyor."""
    types = _types([HumanMessage(content="x"), _call(), _answer(), AIMessage(content="ok")])
    assert "custom_tool_start" not in types
    assert "custom_tool_delta" not in types


def test_an_unanswered_question_draws_nothing_at_all():
    """E4: duraklama sürüyor; kart bekleyen interrupt'tan geliyor."""
    types = _types([HumanMessage(content="rapor hazırla"), _call()])
    assert "user_clarification" not in types
    assert "custom_tool_start" not in types


def test_free_text_comes_back_as_an_unanswered_card():
    objs = _objs(
        [
            HumanMessage(content="x"),
            _call(),
            _answer(artifact={"answered": False, "text": "boşver"}, content="did not answer"),
            AIMessage(content="Peki."),
        ]
    )
    lock = next(o for o in objs if o["type"] == "user_clarification_answered")
    assert lock["answered"] is False and lock["text"] == "boşver"


def test_a_missing_artifact_still_shows_what_was_asked():
    """E21: eksik çizim, hiç çizmemekten iyi bir gerileme."""
    objs = _objs([HumanMessage(content="x"), _call(), _answer(artifact=False), AIMessage("ok")])
    assert any(o["type"] == "user_clarification" for o in objs)


def test_a_rejected_call_leaves_no_card_behind():
    messages = [
        HumanMessage(content="x"),
        _call(questions=[]),
        _answer(artifact={"error": "at least one"}, content="rejected"),
        AIMessage(content="ok"),
    ]
    assert "user_clarification" not in _types(messages)


def test_the_card_and_its_lock_share_one_timeline_turn():
    """K8: soru ve cevabı tek kart; ikiye bölünmüş bir kart okunmuyor."""
    _, packets_2d = reconstruct_messages(
        [HumanMessage(content="x"), _call(), _answer(), AIMessage(content="ok")], {}, "s1"
    )
    turns = {
        p["obj"]["type"]: p["placement"]["turn_index"]
        for turn in packets_2d
        for p in turn
        if isinstance(p, dict) and p["obj"].get("type", "").startswith("user_clarification")
    }
    assert turns["user_clarification"] == turns["user_clarification_answered"]


def test_a_conversation_without_the_tool_is_untouched():
    """Regresyon: aracın varlığı mevcut sohbetlerin çıktısını değiştirmiyor."""
    messages = [
        HumanMessage(content="merhaba"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_time", "args": {}, "id": "t1"}],
        ),
        ToolMessage(content="12:00", name="get_time", tool_call_id="t1"),
        AIMessage(content="Saat 12."),
    ]
    assert _types(messages).count("custom_tool_start") == 1


def test_the_card_survives_the_checkpoint_tree_walk():
    """`get_chat_session` reconstructs from the checkpoint HISTORY, not a flat
    list — a separate walker that clones its state per checkpoint. The
    `ask_user` args are parked on that state by the `model` checkpoint and
    read back by the `clarify` checkpoint one step later, so the clone must
    carry them across or the answered card vanishes on reload while the live
    stream still showed it.
    """
    human = HumanMessage(content="rapor hazırla")
    ask = _call("cx")
    ans = _answer("cx")
    final = AIMessage(content="Hazırladım.")

    checkpoints = [
        {"checkpoint_id": "c1", "parent_checkpoint_id": None, "messages": [human]},
        {"checkpoint_id": "c2", "parent_checkpoint_id": "c1", "messages": [human, ask]},
        {"checkpoint_id": "c3", "parent_checkpoint_id": "c2", "messages": [human, ask, ans]},
        {
            "checkpoint_id": "c4",
            "parent_checkpoint_id": "c3",
            "messages": [human, ask, ans, final],
        },
    ]

    _, packets_2d = reconstruct_message_tree(checkpoints, {}, "s1")
    types = [p["obj"].get("type") for turn in packets_2d for p in turn if isinstance(p, dict)]

    assert "user_clarification" in types
    assert "user_clarification_answered" in types
    assert "custom_tool_start" not in types


def test_a_paused_turn_keeps_its_reasoning_turn():
    """The reload the user actually sees: timeline first, then the card.

    The card itself is appended by `chat_controller` from the pending
    interrupt, so it is absent here by design (E4). What must survive is
    everything the model did BEFORE it asked — that is what went missing when
    the pause discarded the node's writes.
    """
    messages = [
        HumanMessage(content="rapor hazırla"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "Hangi veriyi istiyor?"},
            tool_calls=[{"name": "ask_user", "args": {"questions": QUESTIONS}, "id": "c1"}],
        ),
    ]

    types = _types(messages)

    assert "reasoning_start" in types and "reasoning_delta" in types
    # The synthetic pair is what tells the client this turn finished streaming.
    assert "message_start" in types and "stop" in types
    # ...and still no generic tool card, and no card drawn twice.
    assert "custom_tool_start" not in types
    assert "user_clarification" not in types
