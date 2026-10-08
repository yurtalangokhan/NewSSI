"""The model factory cache must not grow with whatever name a request supplies.

`get_model` was wrapped in `functools.cache`, which never evicts, and its key
is the *raw* argument — normalisation happens inside the function. `model` is
one of the few keys a client may legitimately put in `agent_config`, so a
caller sending a fresh string each turn added a permanent entry (and a live
client object) every time.
"""

from infrastructure.llm.llm import get_model

MAX = 64


def test_the_cache_is_bounded():
    info = get_model.cache_info()

    assert info.maxsize is not None, "get_model's cache is unbounded"
    assert info.maxsize <= 256


def test_the_cache_stops_growing_past_its_bound(monkeypatch):
    monkeypatch.setattr("infrastructure.llm.llm._normalize_model_name", lambda n: "fake")

    class _Registry:
        def initialize(self):
            return None

        def get_provider_for_model(self, *a, **k):
            return None

        def resolve(self, *a, **k):
            return None

    monkeypatch.setattr("infrastructure.llm.adapters.registry.provider_registry", _Registry())
    get_model.cache_clear()

    for i in range(MAX * 3):
        try:
            get_model(f"model-{i}")
        except Exception:
            pass

    assert get_model.cache_info().currsize <= get_model.cache_info().maxsize
