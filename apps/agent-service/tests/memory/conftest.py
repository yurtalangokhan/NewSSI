import pytest


@pytest.fixture(autouse=True)
def _extraction_uses_the_model_the_test_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep memory unit tests independent of the deployment's model choice.

    `MEMORY_EXTRACTION_MODEL` routes extraction to its own model, resolved
    through `get_model`. That is the point of the setting, but it means a
    populated `configs/.env` makes every test in this directory reach the
    provider registry and the real Ollama host instead of the fake model the
    test handed in -- turning unit tests into slow, networked, flaky ones.

    Tests that are actually about model selection set the value themselves;
    `monkeypatch.setenv` applies theirs after this fixture, so they are unaffected.
    """
    monkeypatch.delenv("MEMORY_EXTRACTION_MODEL", raising=False)
