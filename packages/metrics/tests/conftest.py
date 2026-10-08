"""Isolate each test from the process-wide collectors.

``REGISTRY`` is module-level by design — services register once at import time —
so without this the label children of one test leak into the next.
"""

import pytest

from metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUEST_ERRORS_TOTAL,
    HTTP_REQUESTS_TOTAL,
    IDEMPOTENCY_DECISIONS_TOTAL,
    IDEMPOTENCY_LOCK_WAIT_SECONDS,
)


@pytest.fixture(autouse=True)
def _reset_collectors():
    for collector in (
        HTTP_REQUESTS_TOTAL,
        HTTP_REQUEST_DURATION_SECONDS,
        HTTP_REQUEST_ERRORS_TOTAL,
        IDEMPOTENCY_DECISIONS_TOTAL,
        IDEMPOTENCY_LOCK_WAIT_SECONDS,
    ):
        collector.clear()
    yield
