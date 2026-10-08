"""The interactive API docs are off unless a deployment asks for them.

/docs and /redoc enumerate every route and schema this service has, the
internal ones included -- a map of the attack surface, published
unauthenticated. That is a fine trade in development and a poor one
anywhere else.

The setting existed, but defaulted to on, so the safe configuration was the
one an operator had to remember to write down: every deployment that never
set ENABLE_API_DOCS published them. Defaulting to off inverts that -- the
convenience now costs a line in a dev .env, and forgetting costs nothing.
"""

from __future__ import annotations

import pytest
from config_manager import env


def test_docs_are_off_unless_asked_for(monkeypatch) -> None:
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)

    assert env.ENABLE_API_DOCS is False


@pytest.mark.parametrize("value", ["true", "True", "1", "yes"])
def test_a_deployment_can_still_turn_them_on(monkeypatch, value: str) -> None:
    monkeypatch.setenv("ENABLE_API_DOCS", value)

    assert env.ENABLE_API_DOCS is True


def test_the_app_publishes_no_docs_urls_by_default(monkeypatch) -> None:
    from src import main

    monkeypatch.setattr(main, "_docs_enabled", lambda: False)
    app = main.create_app()

    assert app.docs_url is None
    assert app.redoc_url is None


def test_the_app_publishes_docs_urls_when_enabled(monkeypatch) -> None:
    from src import main

    monkeypatch.setattr(main, "_docs_enabled", lambda: True)
    app = main.create_app()

    assert app.docs_url is not None
