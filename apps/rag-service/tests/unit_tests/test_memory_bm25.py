"""Unit tests for the Turkish-aware BM25 domain module (src.memory.bm25)."""

from __future__ import annotations

from src.memory.bm25 import (
    BM25Okapi,
    normalize_turkish,
    tokenize_turkish,
)


def test_folds_turkish_diacritics_and_case() -> None:
    assert normalize_turkish("İSTANBUL") == "istanbul"
    assert normalize_turkish("ışık") == "isik"
    assert normalize_turkish("şeker") == "seker"
    assert normalize_turkish("ağaç") == "agac"
    assert normalize_turkish("üzüm") == "uzum"
    assert normalize_turkish("ördek") == "ordek"
    assert normalize_turkish("çiçek") == "cicek"


def test_handles_punctuation_and_whitespace() -> None:
    normalized = normalize_turkish("  Ben, 2004 doğumluyum!  ")
    assert normalized == "ben, 2004 dogumluyum!"


def test_extracts_normalized_words_and_stems() -> None:
    words, stems = tokenize_turkish("Ben 2004 doğumluyum")
    assert words == ["ben", "2004", "dogumluyum"]
    assert stems == ["ben", "2004", "dogum"]


def test_matches_inflected_forms_via_prefix_stems() -> None:
    _, fact_stems = tokenize_turkish("Ben 2004 doğumluyum")
    _, query_stems = tokenize_turkish("doğum tarihim nedir?")
    overlap = set(fact_stems) & set(query_stems)
    assert "dogum" in overlap


def test_empty_string_returns_empty_lists() -> None:
    words, stems = tokenize_turkish("   ")
    assert words == []
    assert stems == []


def test_exact_match_scores_higher_than_unmatched() -> None:
    corpus = [
        "Ben 2004 doğumluyum",
        "Bilim kurgu ve polisiye romanları severim",
        "Kayseri'de yaşıyorum",
    ]
    bm25 = BM25Okapi.from_documents(corpus)
    scores = bm25.score_all("hangi türden romanları seversin?")

    assert scores[1] > scores[0]
    assert scores[1] > scores[2]
    assert scores[0] == 0.0


def test_inflected_overlap_scores_positively() -> None:
    corpus = ["Ben 2004 doğumluyum"]
    bm25 = BM25Okapi.from_documents(corpus)
    scores = bm25.score_all("doğum günün ne zaman?")
    assert scores[0] > 0.0


def test_completely_irrelevant_query_scores_zero() -> None:
    corpus = ["Ben 2004 doğumluyum"]
    bm25 = BM25Okapi.from_documents(corpus)
    scores = bm25.score_all("hangi türden romanları seversin?")
    assert scores[0] == 0.0


def test_empty_corpus_returns_empty_scores() -> None:
    bm25 = BM25Okapi.from_documents([])
    assert bm25.score_all("herhangi bir soru") == []
