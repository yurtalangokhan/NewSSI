"""Behavioural contract for CircuitBreaker's CLOSED/OPEN/HALF_OPEN state machine.

Half-open closing must require every admitted trial call to succeed, not
just the first one to report: with half_open_max_calls > 1, several trial
calls can be in flight at once, and a single lucky success must not declare
the dependency healthy while a sibling trial is still failing.
"""

import asyncio

import pytest

from security.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerOpenException,
    CircuitState,
)


def _breaker(**overrides) -> CircuitBreaker:
    kwargs = {
        "name": "test-dep",
        "failure_threshold": 3,
        "reset_timeout_seconds": 30.0,
        "half_open_max_calls": 2,
    }
    kwargs.update(overrides)
    return CircuitBreaker(**kwargs)


class TestClosedState:
    async def test_starts_closed(self):
        assert _breaker().state == CircuitState.CLOSED

    async def test_acquire_is_allowed_while_closed(self):
        breaker = _breaker()
        await breaker.acquire()  # must not raise

    async def test_failures_below_threshold_stay_closed(self):
        breaker = _breaker(failure_threshold=3)
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    async def test_success_resets_the_failure_count(self):
        breaker = _breaker(failure_threshold=3)
        await breaker.record_failure()
        await breaker.record_failure()
        await breaker.record_success()
        await breaker.record_failure()
        await breaker.record_failure()
        # Two more failures after the reset must not reach a threshold of 3.
        assert breaker.state == CircuitState.CLOSED

    async def test_reaching_the_threshold_opens_the_circuit(self):
        breaker = _breaker(failure_threshold=3)
        await breaker.record_failure()
        await breaker.record_failure()
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN


class TestOpenState:
    async def test_acquire_raises_while_open_and_within_the_reset_window(self):
        breaker = _breaker(failure_threshold=1, reset_timeout_seconds=30.0)
        await breaker.record_failure()

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.acquire()

    async def test_open_error_carries_the_breaker_name_and_remaining_seconds(self):
        breaker = _breaker(name="payments", failure_threshold=1, reset_timeout_seconds=30.0)
        await breaker.record_failure()

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await breaker.acquire()

        assert exc_info.value.name == "payments"
        assert 0 < exc_info.value.reset_in_seconds <= 30.0
        assert "payments" in str(exc_info.value)

    async def test_open_error_is_also_catchable_as_the_legacy_alias(self):
        breaker = _breaker(failure_threshold=1, reset_timeout_seconds=30.0)
        await breaker.record_failure()

        with pytest.raises(CircuitBreakerOpenException):
            await breaker.acquire()

    async def test_transitions_to_half_open_once_the_reset_window_elapses(self):
        breaker = _breaker(failure_threshold=1, reset_timeout_seconds=0.01)
        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(0.02)
        await breaker.acquire()  # must not raise
        assert breaker.state == CircuitState.HALF_OPEN


class TestHalfOpenState:
    def _opened_breaker(self, **overrides) -> CircuitBreaker:
        overrides.setdefault("reset_timeout_seconds", 0.0)
        breaker = _breaker(**overrides)
        breaker.state = CircuitState.OPEN
        breaker.failure_count = breaker.failure_threshold
        breaker.last_state_change -= 1  # already elapsed the (zero) reset window
        return breaker

    async def test_first_admitted_call_flips_state_to_half_open(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        assert breaker.state == CircuitState.HALF_OPEN

    async def test_admits_up_to_half_open_max_calls_concurrently(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()  # second concurrent trial, must not raise

    async def test_rejects_calls_beyond_half_open_max_calls(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.acquire()

    async def test_single_trial_call_succeeding_closes_the_circuit(self):
        breaker = self._opened_breaker(half_open_max_calls=1)
        await breaker.acquire()
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    async def test_any_trial_failure_reopens_immediately(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    async def test_does_not_close_while_a_sibling_trial_is_still_in_flight(self):
        # Two trials admitted; only one has reported back so far. The
        # breaker must not declare the dependency healthy until the second
        # trial's outcome is known too.
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        await breaker.record_success()  # first trial reports success
        assert breaker.state == CircuitState.HALF_OPEN

    async def test_closes_only_once_every_admitted_trial_has_succeeded(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        await breaker.record_success()
        await breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    async def test_a_late_failure_from_a_sibling_trial_reopens_even_after_one_success(self):
        # This is the regression case: a lucky first success must not mask
        # a concurrent trial that goes on to fail.
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        await breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN  # not yet closed

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    async def test_a_late_success_after_a_sibling_failure_already_reopened_is_a_no_op(self):
        breaker = self._opened_breaker(half_open_max_calls=2)
        await breaker.acquire()
        await breaker.acquire()

        await breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        await breaker.record_success()
        assert breaker.state == CircuitState.OPEN

    async def test_closing_resets_the_failure_count(self):
        breaker = self._opened_breaker(half_open_max_calls=1)
        assert breaker.failure_count == breaker.failure_threshold
        await breaker.acquire()
        await breaker.record_success()
        assert breaker.failure_count == 0

    async def test_a_fresh_half_open_window_after_reopening_accepts_trials_again(self):
        breaker = self._opened_breaker(half_open_max_calls=2, reset_timeout_seconds=0.01)
        await breaker.acquire()
        await breaker.acquire()
        await breaker.record_failure()  # reopens
        assert breaker.state == CircuitState.OPEN

        await asyncio.sleep(0.02)
        await breaker.acquire()  # new half-open window must admit trials again
        assert breaker.state == CircuitState.HALF_OPEN


class TestAsyncContextManager:
    async def test_successful_call_is_recorded_as_a_success(self):
        breaker = _breaker(failure_threshold=3)
        async with breaker:
            pass
        assert breaker.failure_count == 0

    async def test_raised_exception_is_recorded_as_a_failure_and_reraised(self):
        breaker = _breaker(failure_threshold=3)
        with pytest.raises(ValueError):
            async with breaker:
                raise ValueError("boom")
        assert breaker.failure_count == 1

    async def test_repeated_failures_through_the_context_manager_open_the_circuit(self):
        breaker = _breaker(failure_threshold=2)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                async with breaker:
                    raise RuntimeError("boom")
        assert breaker.state == CircuitState.OPEN

    async def test_open_circuit_raises_before_the_guarded_body_runs(self):
        breaker = _breaker(failure_threshold=1, reset_timeout_seconds=30.0)
        await breaker.record_failure()

        entered = False
        with pytest.raises(CircuitBreakerOpenError):
            async with breaker:
                entered = True
        assert entered is False


class TestConcurrency:
    async def test_concurrent_failures_do_not_lose_updates(self):
        breaker = _breaker(failure_threshold=1_000_000)
        await asyncio.gather(*(breaker.record_failure() for _ in range(50)))
        assert breaker.failure_count == 50
