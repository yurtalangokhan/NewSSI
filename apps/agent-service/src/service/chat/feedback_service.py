"""Preserve the existing feedback acknowledgement behavior."""

from core.observability.logger import get_logger

logger = get_logger(__name__)


def accept_feedback(run_id: str, key: str) -> dict[str, str]:
    logger.info("Feedback received for run %s with key %s", run_id, key)
    return {"run_id": run_id, "key": key}
