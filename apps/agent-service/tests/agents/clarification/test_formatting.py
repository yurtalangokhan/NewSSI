"""Resume değeri → modelin okuyacağı metin.

Buradaki metin modele gidiyor, kullanıcıya değil: sarmalayıcı cümleler
İngilizce (K6 ile aynı gerekçe), soru ve şık metinleri kullanıcının
dilinde geldiği gibi kalıyor.
"""

from agents.clarification.formatting import format_resume

QUESTIONS = [
    {"header": "Hedef kitle", "question": "Kim okuyacak?", "options": [], "multiSelect": False},
    {"header": "Biçim", "question": "Nasıl olsun?", "options": [], "multiSelect": True},
]


def test_a_single_choice_reads_as_header_and_label():
    text = format_resume(QUESTIONS, {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}})
    assert "Hedef kitle: Yönetim" in text


def test_multiple_selections_are_joined():
    text = format_resume(
        QUESTIONS, {"answered": True, "answers": {"Biçim": ["Kısa özet", "Tam metin"]}}
    )
    assert "Biçim: Kısa özet, Tam metin" in text


def test_an_empty_selection_means_the_user_left_it_to_the_agent():
    """Arayüzün "Sen karar ver" şıkkı boş liste gönderiyor — sihirli metin yok."""
    text = format_resume(QUESTIONS, {"answered": True, "answers": {"Hedef kitle": []}})
    assert "Hedef kitle" in text and "left this" in text.lower()


def test_a_question_with_no_answer_at_all_is_treated_the_same_way():
    text = format_resume(QUESTIONS, {"answered": True, "answers": {"Hedef kitle": ["Yönetim"]}})
    assert "Biçim" in text and "left this" in text.lower()


def test_questions_keep_their_asked_order():
    text = format_resume(
        QUESTIONS,
        {"answered": True, "answers": {"Biçim": ["Kısa"], "Hedef kitle": ["Yönetim"]}},
    )
    assert text.index("Hedef kitle") < text.index("Biçim")


def test_free_text_is_reported_as_not_an_answer():
    """K4: hangi soruya cevap verildiği TAHMİN EDİLMİYOR."""
    text = format_resume(QUESTIONS, {"answered": False, "text": "boşver, hava durumu ne?"})
    assert "did not answer" in text.lower()
    assert "boşver, hava durumu ne?" in text
    assert "Hedef kitle:" not in text


def test_an_unanswered_resume_without_text_still_reads_sensibly():
    text = format_resume(QUESTIONS, {"answered": False})
    assert "did not answer" in text.lower()


def test_a_malformed_resume_does_not_raise():
    """Resume dış dünyadan geliyor; şekli bozuksa araç patlamamalı."""
    assert format_resume(QUESTIONS, None)
    assert format_resume(QUESTIONS, "evet")
    assert format_resume(QUESTIONS, {"answered": True, "answers": "Yönetim"})


def test_answers_are_normalised_for_the_artifact():
    from agents.clarification.formatting import normalise_resume

    assert normalise_resume({"answered": True, "answers": {"Hedef kitle": "Yönetim"}}) == {
        "answered": True,
        "answers": {"Hedef kitle": ["Yönetim"]},
    }
    assert normalise_resume({"answered": False, "text": "yok"}) == {
        "answered": False,
        "text": "yok",
    }
    assert normalise_resume(None) == {"answered": False, "text": ""}
