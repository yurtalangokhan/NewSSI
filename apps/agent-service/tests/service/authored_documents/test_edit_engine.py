import pytest

from core.exceptions.authored_documents import EditApplicationError
from core.types.authored_documents import EditOp
from service.authored_documents.edit_engine import apply_edits

DOC = "| Belge kontrolü | 2 iş günü |\n| Finans onayı | 2 iş günü |\n\nSon paragraf."


def test_edits_apply_sequentially() -> None:
    result = apply_edits(
        DOC,
        [
            EditOp("| Belge kontrolü | 2 iş günü |", "| Belge kontrolü | 1 iş günü |"),
            EditOp("Son paragraf.", "Son paragraf güncellendi."),
        ],
    )
    assert "| Belge kontrolü | 1 iş günü |" in result
    assert result.endswith("Son paragraf güncellendi.")


def test_ambiguous_match_fails_and_reports_count() -> None:
    with pytest.raises(EditApplicationError) as caught:
        apply_edits(DOC, [EditOp("2 iş günü", "3 iş günü")])
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.reason == "ambiguous"
    assert diagnostic.match_count == 2


def test_replace_all_allows_multiple_matches() -> None:
    assert apply_edits(DOC, [EditOp("2 iş günü", "3 iş günü", replace_all=True)]).count("3 iş günü") == 2


def test_all_failures_are_reported_and_nothing_is_applied() -> None:
    with pytest.raises(EditApplicationError) as caught:
        apply_edits(
            DOC,
            [
                EditOp("Son paragraf.", "X"),
                EditOp("| Finans onay | 2 iş günü |", "Y"),
                EditOp("", "Z"),
            ],
        )
    reasons = [(d.index, d.reason) for d in caught.value.diagnostics]
    assert reasons == [(1, "not_found"), (2, "empty_old_str")]
    assert caught.value.diagnostics[0].closest == "| Finans onayı | 2 iş günü |"


def test_identical_replacement_is_a_no_change_failure() -> None:
    with pytest.raises(EditApplicationError) as caught:
        apply_edits(DOC, [EditOp("Son paragraf.", "Son paragraf.")])
    assert caught.value.diagnostics[0].reason == "no_change"


def test_later_edit_sees_earlier_edit_output() -> None:
    result = apply_edits("A", [EditOp("A", "B"), EditOp("B", "C")])
    assert result == "C"


SECTIONED = "Bir\n\n---\n\nİki\n\n---\n\nÜç"


def test_replace_all_that_expands_its_own_anchor_is_rejected() -> None:
    with pytest.raises(EditApplicationError) as caught:
        apply_edits(SECTIONED, [EditOp("---", "## Yeni bölüm\n\n---", replace_all=True)])
    (diagnostic,) = caught.value.diagnostics
    assert diagnostic.reason == "replace_all_insert"
    assert diagnostic.match_count == 2


def test_replace_all_rename_still_applies_everywhere() -> None:
    assert apply_edits("a1 a1", [EditOp("a1", "b2", replace_all=True)]) == "b2 b2"


def test_expanding_a_single_match_without_replace_all_is_still_allowed() -> None:
    assert apply_edits(SECTIONED, [EditOp("Üç", "Üç\n\nDört")]).endswith("Üç\n\nDört")


def test_replace_all_expanding_a_single_match_is_allowed() -> None:
    assert apply_edits("Bir\n\n---", [EditOp("---", "Yeni\n\n---", replace_all=True)]).endswith("Yeni\n\n---")
