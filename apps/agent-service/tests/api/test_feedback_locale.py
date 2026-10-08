"""Feedback acknowledgements are translated in both supported languages."""

from pathlib import Path

from localization import LocaleManager
import pytest


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("en", "Feedback received."), ("tr", "Geri bildiriminiz alındı.")],
)
def test_feedback_acknowledgement_is_translated(locale: str, expected: str) -> None:
    manager = LocaleManager()
    manager.load_directory(Path(__file__).resolve().parents[2] / "locales")

    assert manager.translate("agent.feedback_received", locale=locale) == expected
