"""get_model must decide on the *running* loop, not the "current" one.

``get_model`` is sync but the provider registry is async, so it has to know
whether it is being called from inside a running event loop: if it is, it
cannot block on the registry and falls back to a direct provider lookup; if
it is not, it may drive the registry to completion itself.

It asked ``asyncio.get_event_loop()``, which answers a different question --
"is a loop installed as current for this thread" -- and that is
process-global, deprecated, and outlives whoever set it. Any earlier async
work in the same process left one installed, after which a perfectly
ordinary synchronous call took the in-a-loop branch and quietly skipped the
registry. In a test run that shows up as a failure that only appears when
another test ran first; in the service it means which model you get can
depend on what the worker did before.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from infrastructure.llm.llm import get_model


def _registry_returning(provider) -> Mock:
    registry = Mock()
    registry.initialize.return_value = None
    registry.find_model = AsyncMock(return_value=(provider, {"name": "demo-model"}))
    return registry


def _provider() -> Mock:
    provider = Mock()
    provider.get_model_instance.return_value = "model-instance"
    return provider


def test_a_stale_current_loop_does_not_look_like_a_running_one() -> None:
    """The exact leak: a loop installed as current by earlier async work."""
    get_model.cache_clear()
    provider = _provider()

    stale = asyncio.new_event_loop()
    asyncio.set_event_loop(stale)
    try:
        with patch(
            "infrastructure.llm.adapters.registry.provider_registry", _registry_returning(provider)
        ):
            model = get_model("demo-model")
    finally:
        asyncio.set_event_loop(None)
        stale.close()

    assert model == "model-instance"
    provider.get_model_instance.assert_called_once_with("demo-model")


def test_no_current_loop_at_all_still_reaches_the_registry() -> None:
    get_model.cache_clear()
    provider = _provider()

    asyncio.set_event_loop(None)
    with patch(
        "infrastructure.llm.adapters.registry.provider_registry", _registry_returning(provider)
    ):
        model = get_model("demo-model")

    assert model == "model-instance"


@pytest.mark.asyncio
async def test_inside_a_running_loop_it_uses_the_direct_lookup() -> None:
    """Blocking on the registry here would deadlock the loop it is called from."""
    get_model.cache_clear()

    with (
        patch(
            "infrastructure.llm.adapters.registry.provider_registry",
            _registry_returning(_provider()),
        ),
        patch("infrastructure.llm.llm._get_model_direct", return_value="direct-instance") as direct,
    ):
        model = get_model("demo-model")

    assert model == "direct-instance"
    direct.assert_called_once_with("demo-model")
