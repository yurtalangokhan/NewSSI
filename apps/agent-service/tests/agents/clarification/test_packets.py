"""Paketler — özellikle geçmiş tarafındaki çift.

Buradaki asıl iddia şu: geçmiş paketleri kurulurken HİÇBİR METİN
AYRIŞTIRILMIYOR. Ayrıştırmaya dayanan bir tasarım, modelin metni biraz
farklı yazdığı ilk günde sessizce bozulurdu.
"""

from agents.clarification.packets import (
    answered_packet,
    clarification_packet,
    packet_from_interrupt,
    packets_for_history,
)

ARGS = {
    "questions": [
        {
            "question": "Raporu kim okuyacak?",
            "header": "Hedef kitle",
            "options": [{"label": "Yönetim"}, {"label": "Teknik ekip"}],
        }
    ]
}


def test_the_question_packet_carries_a_version_and_a_request_id():
    packet = clarification_packet("i1", ARGS["questions"], ["Fatura Uzmanı"])
    assert packet["type"] == "user_clarification"
    assert packet["v"] == 1
    assert packet["request_id"] == "i1"
    assert packet["agent_path"] == ["Fatura Uzmanı"]


def test_an_answered_packet_carries_the_selections():
    packet = answered_packet("i1", {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}})
    assert packet["answered"] is True
    assert packet["answers"] == {"Hedef kitle": ["Yönetim"]}
    assert "text" not in packet


def test_an_unanswered_packet_carries_what_was_said_instead():
    packet = answered_packet("i1", {"answered": False, "text": "boşver"})
    assert packet["answered"] is False
    assert packet["text"] == "boşver"
    assert "answers" not in packet


def test_a_pending_interrupt_becomes_a_question_packet():
    value = {"type": "user_clarification", "v": 1, "questions": ARGS["questions"], "agent_path": []}
    packet = packet_from_interrupt(value, "i9")
    assert packet["request_id"] == "i9"
    assert packet["questions"][0]["header"] == "Hedef kitle"


def test_a_malformed_interrupt_draws_nothing():
    assert packet_from_interrupt("düz metin", "i9") is None


def test_history_rebuilds_the_pair_from_structured_data_only():
    """E5: sorular args'tan, cevaplar artifact'tan."""
    card, lock = packets_for_history(
        "c1", ARGS, {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}}
    )
    assert card["type"] == "user_clarification" and card["request_id"] == "c1"
    assert lock["type"] == "user_clarification_answered" and lock["request_id"] == "c1"
    assert lock["answers"] == {"Hedef kitle": ["Yönetim"]}


def test_a_rejected_call_leaves_no_trace_in_history():
    """Doğrulama hatası duraklama açmadı; kullanıcı hiçbir şey görmemişti."""
    assert packets_for_history("c1", {"questions": []}, {"error": "..."}) is None
    assert packets_for_history("c1", {"questions": []}, None) is None
    assert packets_for_history("c1", None, None) is None


def test_a_missing_artifact_still_draws_the_questions():
    """E21: eksik çizmek, hiç çizmemekten iyi bir gerileme."""
    card, lock = packets_for_history("c1", ARGS, None)
    assert card["questions"][0]["header"] == "Hedef kitle"
    assert lock["answered"] is False
