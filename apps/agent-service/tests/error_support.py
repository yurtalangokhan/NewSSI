"""Assertions on the localized text of typed application errors (agent-service).

Service code raises ``ApplicationError`` subclasses that carry a catalog key;
the human-readable text is rendered at the transport boundary. Tests that care
about the wording assert on that rendering, in a fixed locale, instead of on
``str(error)``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import re

from error_contract import ApplicationError, render_error_message
import pytest


@contextmanager
def raises_localized(
    error_type: type[ApplicationError], pattern: str, *, locale: str = "en"
) -> Iterator[pytest.ExceptionInfo[ApplicationError]]:
    """``pytest.raises`` whose ``match`` applies to the rendered, localized message."""
    with pytest.raises(error_type) as info:
        yield info
    text = render_error_message(info.value, locale=locale)
    assert re.search(pattern, text), f"{text!r} does not match {pattern!r}"
