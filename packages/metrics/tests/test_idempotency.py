"""Contract for the idempotency decision collectors.

The label rules mirror ``registry.py``: ``route`` carries the route template,
never the resolved path, so a parameterised endpoint stays one time series no
matter how many ids flow through it. ``outcome`` is a closed enum — a free-form
label here would let one bad caller grow the series without bound.

The tests drive the recorder with structurally-compatible decision objects on
purpose: ``metrics`` must not import ``idempotency``, and the real middleware
wiring is exercised by the services in T6.
"""

from metrics import (
    install_idempotency_recorder,
    metrics_response,
)

SERVICE = "test-service"
CHAT_ROUTE = "/api/v1/chat/sessions/{chat_session_id}/messages"


class _Decision:
    """Structural stand-in for ``idempotency.models.IdempotencyDecision``."""

    def __init__(
        self,
        outcome: str,
        route_template: str | None = CHAT_ROUTE,
        wait_ms: float | None = None,
    ) -> None:
        self.outcome = outcome
        self.route_template = route_template
        self.wait_ms = wait_ms


def _sample(text: str, metric: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(metric)]


def _outcomes(payload: str) -> set[str]:
    """Parse the ``outcome`` label from every sample line.

    The first label sits behind the ``{`` of the metric name, so the line is
    stripped of its prefix before the label split.
    """
    values: set[str] = set()
    for line in _sample(payload, "idempotency_decisions_total"):
        if "{" not in line:
            continue
        for part in line.split("{", 1)[1].split(","):
            if part.startswith('outcome="'):
                values.add(part.split('="')[1].rstrip('"'))
    return values


def test_both_series_render_with_expected_label_sets() -> None:
    recorder = install_idempotency_recorder(SERVICE)
    recorder(_Decision("executed", wait_ms=12.0))

    payload = metrics_response().body.decode()

    decision_lines = _sample(payload, "idempotency_decisions_total")
    assert decision_lines, "the decisions counter must be exported"
    assert any('outcome="executed"' in line for line in decision_lines)
    assert any('service="test-service"' in line for line in decision_lines)
    assert any(f'route="{CHAT_ROUTE}"' in line for line in decision_lines)

    wait_lines = _sample(payload, "idempotency_lock_wait_seconds")
    assert wait_lines, "the lock-wait histogram must be exported"
    assert any('service="test-service"' in line for line in wait_lines)
    assert any(f'route="{CHAT_ROUTE}"' in line for line in wait_lines)


def test_wait_histogram_skips_decisions_without_a_wait() -> None:
    """Only decisions that actually waited on the lock carry a timing. With no
    observation at all, prometheus_client emits no sample lines — so the
    absence of the series is itself the proof."""
    recorder = install_idempotency_recorder(SERVICE)
    recorder(_Decision("executed", wait_ms=None))

    payload = metrics_response().body.decode()

    assert _sample(payload, "idempotency_lock_wait_seconds_count") == [], (
        "a decision without wait_ms must not add an observation"
    )


def test_route_label_is_used_verbatim() -> None:
    """The recorder labels with exactly what it receives — it neither derives
    nor rewrites the route. Keeping resolved ids out of the label is the
    middleware's contract (``route_template`` from the policy match), asserted
    in the idempotency package's own tests; this test locks the pass-through
    so a future "helpful" normalisation cannot silently change cardinality."""
    recorder = install_idempotency_recorder(SERVICE)
    recorder(_Decision("executed", route_template=CHAT_ROUTE))
    recorder(_Decision("replayed", route_template=CHAT_ROUTE))

    payload = metrics_response().body.decode()

    routes = {
        part
        for line in _sample(payload, "idempotency_decisions_total")
        for part in line.split(",")
        if part.startswith('route="')
    }
    assert routes == {f'route="{CHAT_ROUTE}"'}


def test_outcome_label_is_the_closed_enum() -> None:
    """Every outcome value must come from the known enum, so a typo in a new
    outcome fails here instead of silently growing the series."""
    known = {
        "executed",
        "replayed",
        "bypassed",
        "key_required",
        "key_invalid",
        "conflict",
        "in_flight",
        "completed_no_replay",
        "store_unavailable",
    }
    recorder = install_idempotency_recorder(SERVICE)
    for outcome in sorted(known):
        recorder(_Decision(outcome))

    assert _outcomes(metrics_response().body.decode()) == known


def test_missing_route_template_falls_back_to_the_constant() -> None:
    recorder = install_idempotency_recorder(SERVICE)
    recorder(_Decision("bypassed", route_template=None))

    payload = metrics_response().body.decode()

    assert any(
        'route="<default>"' in line
        for line in _sample(payload, "idempotency_decisions_total")
    )


def test_recorder_swallows_internal_errors() -> None:
    """A raising collector must not break the request it observes."""

    class Broken:
        outcome = "executed"

        @property
        def route_template(self) -> str:
            raise RuntimeError("boom")

        wait_ms = None

    install_idempotency_recorder(SERVICE)(Broken())
