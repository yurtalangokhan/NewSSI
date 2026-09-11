"""Model hata yapabilir; doğrulama onu düzeltebilsin diye var.

Bu yüzden hiçbir doğrulama exception fırlatmıyor — hepsi modele geri
dönecek bir metne çevriliyor (bkz. test_tool.py).
"""

import pytest

from agents.clarification.schema import InvalidQuestions, validate_questions

VALID = [
    {
        "question": "Raporu kim okuyacak?",
        "header": "Hedef kitle",
        "options": [
            {"label": "Yönetim", "description": "Özet ve sayılar"},
            {"label": "Teknik ekip", "description": "Detay ve metodoloji"},
        ],
    }
]


def _err(questions) -> str:
    with pytest.raises(InvalidQuestions) as exc:
        validate_questions(questions)
    return str(exc.value)


def test_a_valid_question_survives_normalisation():
    (question,) = validate_questions(VALID)
    assert question["header"] == "Hedef kitle"
    assert question["multiSelect"] is False
    assert [o["label"] for o in question["options"]] == ["Yönetim", "Teknik ekip"]


def test_empty_question_list_is_rejected():
    assert "at least one" in _err([]).lower()


def test_more_than_four_questions_is_rejected():
    questions = [dict(VALID[0], header=f"H{i}") for i in range(5)]
    assert "4" in _err(questions)


def test_a_question_needs_at_least_two_options():
    """Tek şık bir seçim değil, bir onay kutusu — aracın işi o değil."""
    assert "2" in _err([dict(VALID[0], options=VALID[0]["options"][:1])])


def test_a_question_may_not_have_more_than_four_options():
    options = [{"label": f"L{i}"} for i in range(5)]
    assert "4" in _err([dict(VALID[0], options=options)])


def test_duplicate_headers_are_rejected():
    """`header` cevap anahtarı; çakışma bir cevabı sessizce yutardı."""
    message = _err([VALID[0], dict(VALID[0])])
    assert "header" in message.lower() and "Hedef kitle" in message


def test_a_blank_header_is_rejected():
    assert "header" in _err([dict(VALID[0], header="  ")]).lower()


def test_a_blank_question_text_is_rejected():
    assert "question" in _err([dict(VALID[0], question="")]).lower()


def test_a_blank_option_label_is_rejected():
    options = [{"label": "Yönetim"}, {"label": ""}]
    assert "label" in _err([dict(VALID[0], options=options)]).lower()


def test_multi_select_is_accepted_in_either_spelling():
    camel, snake = validate_questions(
        [dict(VALID[0], multiSelect=True), dict(VALID[0], header="B", multi_select=True)]
    )
    assert camel["multiSelect"] is True
    assert snake["multiSelect"] is True


def test_a_missing_description_becomes_empty_rather_than_absent():
    """Arayüz alanın var olduğuna güvenebilsin."""
    (question,) = validate_questions([dict(VALID[0], options=[{"label": "A"}, {"label": "B"}])])
    assert [o["description"] for o in question["options"]] == ["", ""]


def test_non_list_input_is_rejected_without_blowing_up():
    assert _err("Hedef kitle nedir?")
    assert _err([{"question": "x"}])


def test_the_ui_option_is_not_expected_from_the_model():
    """ "Sen karar ver" şıkkını arayüz ekliyor; model gönderirse çift olmasın."""
    (question,) = validate_questions(VALID)
    assert len(question["options"]) == 2
