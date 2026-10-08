from prometheus_client import generate_latest
from metrics import REGISTRY

from infrastructure.runtime.chat_runs.prometheus_metrics import PrometheusChatRunMetrics
from service.chat_runs.domain import RunStatus


def _sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_chat_run_signals_are_exported_on_the_service_registry():
    metrics = PrometheusChatRunMetrics()
    active, streams = _sample("chat_runs_active"), _sample("chat_run_event_streams_open")
    finished = _sample("chat_runs_finished_total", status="cancelled", reason="none")

    metrics.run_started()
    metrics.stream_opened()
    metrics.heartbeat_lag(3.0)
    metrics.run_finished(RunStatus.CANCELLED, "none")

    assert _sample("chat_runs_active") == active + 1
    assert _sample("chat_run_event_streams_open") == streams + 1
    assert _sample("chat_runs_finished_total", status="cancelled", reason="none") == finished + 1
    assert b"chat_run_heartbeat_lag_seconds_bucket" in generate_latest(REGISTRY)

    metrics.run_ended()
    metrics.stream_closed()
    assert _sample("chat_runs_active") == active
    assert _sample("chat_run_event_streams_open") == streams
