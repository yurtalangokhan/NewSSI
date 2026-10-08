"""Retry must honour the backoff the policy file declares.

``wait_exponential``'s ``multiplier`` is a coefficient, not the growth base:
passing the policy's ``multiplier: 2.0`` there produced waits of 4s, 8s, 16s,
all clamped to ``maxSeconds``, so every retry waited the maximum and the
configured ``initialSeconds`` never applied.
"""

import httpx
import pytest

from security import bounded_retry, retry_waits


def test_first_wait_matches_the_configured_initial_backoff() -> None:
    waits = retry_waits(max_attempts=4, initial_backoff=0.2, multiplier=2.0, max_backoff=10.0)

    assert waits[0] == pytest.approx(0.2)


def test_waits_grow_by_the_configured_multiplier() -> None:
    waits = retry_waits(max_attempts=4, initial_backoff=0.2, multiplier=2.0, max_backoff=10.0)

    assert waits == pytest.approx([0.2, 0.4, 0.8])


def test_waits_are_capped_by_max_backoff() -> None:
    waits = retry_waits(max_attempts=5, initial_backoff=0.2, multiplier=2.0, max_backoff=0.5)

    assert max(waits) == pytest.approx(0.5)


def test_retry_count_is_bounded_by_max_attempts() -> None:
    attempts = 0

    @bounded_retry(max_attempts=3, initial_backoff=0.0, max_backoff=0.0)
    async def always_fails():
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("boom")

    with pytest.raises(httpx.ConnectError):
        import asyncio

        asyncio.run(always_fails())

    assert attempts == 3


def test_non_transient_errors_are_not_retried() -> None:
    attempts = 0

    @bounded_retry(max_attempts=3, initial_backoff=0.0, max_backoff=0.0)
    async def bad_request():
        nonlocal attempts
        attempts += 1
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(bad_request())

    assert attempts == 1


def test_a_recovering_call_returns_its_value() -> None:
    import asyncio

    attempts = 0

    @bounded_retry(max_attempts=3, initial_backoff=0.0, max_backoff=0.0)
    async def flaky():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("slow")
        return "recovered"

    assert asyncio.run(flaky()) == "recovered"
    assert attempts == 3
