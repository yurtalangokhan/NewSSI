from agents.interrupts.classify import classify_interrupt


def test_flow_human_input_recognised():
    assert classify_interrupt({"type": "human_input", "prompt": "?"}) == "human_input"


def test_hitl_request_recognised_by_shape():
    """HITLRequest'te 'type' alanı YOK — şeklinden tanınmak zorunda."""
    value = {
        "action_requests": [{"name": "send_email", "args": {}}],
        "review_configs": [{"action_name": "send_email", "allowed_decisions": ["approve"]}],
    }
    assert classify_interrupt(value) == "tool_approval"


def test_unknown_shapes_return_none():
    assert classify_interrupt("düz metin prompt") is None
    assert classify_interrupt({"action_requests": []}) is None  # review_configs eksik
    assert classify_interrupt(None) is None


def test_user_clarification_recognised_by_its_type():
    """`ask_user`'ın payload'ı `type` taşıyor — şekilden çıkarım gerekmiyor."""
    value = {
        "type": "user_clarification",
        "v": 1,
        "questions": [{"question": "Kim okuyacak?", "header": "Hedef kitle", "options": []}],
    }
    assert classify_interrupt(value) == "user_clarification"


def test_a_clarification_is_not_mistaken_for_an_approval():
    """İkisi aynı boru hattını paylaşıyor; karışmaları yanlış renderer demek."""
    assert classify_interrupt({"type": "user_clarification"}) == "user_clarification"
    assert (
        classify_interrupt(
            {"action_requests": [], "review_configs": [{"action_name": "x"}]},
        )
        == "tool_approval"
    )
