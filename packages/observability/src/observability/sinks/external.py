"""The base class for any log platform reached over the network.

This is the extension point that makes an external platform a configuration
change. It provides the parts every remote destination needs and that must not
be reinvented per target:

  - a bounded queue, so a slow platform applies backpressure to the queue and
    never to a request
  - a background sender, so a network call never runs on a request thread
  - batching by size or interval, so a platform is not called once per record
  - bounded retries with backoff, so a transient outage does not lose records
  - a drop-oldest policy with a counter, so an unreachable platform degrades
    predictably instead of exhausting memory
  - a bounded flush on shutdown, so a slow platform cannot hold the process open

A target is a subclass that implements :meth:`ExternalSink.send`. That is the
whole cost of adding Elasticsearch, Loki, or OTLP, and it is deliberately kept
small so the choice can be made later without touching this module.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from . import LogSink

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..formatter import BaseFormatter

DEFAULT_BATCH_SIZE = 100
DEFAULT_FLUSH_INTERVAL = 5.0
DEFAULT_MAX_QUEUE = 1000
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
DEFAULT_SHUTDOWN_TIMEOUT = 10.0


class ExternalSink(LogSink):
    """Queue records and deliver them in batches from a worker thread."""

    def __init__(self, *, formatter: BaseFormatter, options: dict[str, Any] | None = None) -> None:
        super().__init__()
        options = options or {}
        self.setFormatter(formatter)
        self.setLevel(logging.NOTSET)
        self.url = str(options.get("url", ""))
        self.batch_size = max(1, int(options.get("batch_size", DEFAULT_BATCH_SIZE)))
        self.flush_interval = float(options.get("flush_interval", DEFAULT_FLUSH_INTERVAL))
        self.max_queue = max(self.batch_size, int(options.get("max_queue", DEFAULT_MAX_QUEUE)))
        self.max_retries = max(0, int(options.get("max_retries", DEFAULT_MAX_RETRIES)))
        self.retry_backoff = float(options.get("retry_backoff", DEFAULT_RETRY_BACKOFF))
        self.shutdown_timeout = float(options.get("shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT))
        self.headers = dict(options.get("headers", {}))
        self.dropped_count = 0
        self.sent_count = 0
        self.failed_count = 0
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=self.max_queue)
        self._worker: threading.Thread | None = None
        self._stopping = threading.Event()
        self._disabled_reason: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def startup(self) -> None:
        """Start the sender thread.

        A deployment that selects the generic ``external`` name without
        registering a target fails here, at startup, rather than discovering the
        mistake from a counter at 3 a.m.
        """
        if type(self).send is ExternalSink.send:
            from ..config import UnknownSinkError

            raise UnknownSinkError(
                "the generic 'external' sink has no delivery target; register a "
                "target-specific subclass with register_sink() or configure a "
                "shipped destination such as 'elasticsearch'"
            )
        if not self.url:
            self._disabled_reason = "no url configured"
            return
        self._stopping.clear()
        self._worker = threading.Thread(
            target=self._run,
            name=f"observability-{type(self).__name__.lower()}",
            daemon=True,
        )
        self._worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        """Queue one record without blocking the calling thread.

        When the queue is full the oldest record is dropped and counted. Dropping
        the oldest keeps the newest information, which is what an operator needs
        during an incident, and it keeps the request path free.
        """
        if self._worker is None or self._disabled_reason:
            return
        try:
            payload = self.fields_for(record)
        except Exception:  # noqa: BLE001 - formatting must not break the caller
            self.handleError(record)
            return
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            self._drop_oldest()
            try:
                self._queue.put_nowait(payload)
            except queue.Full:  # pragma: no cover - only under a full queue race
                self.dropped_count += 1

    def flush(self) -> None:
        """Deliver what is queued now, waiting up to the shutdown timeout."""
        if self._worker is None:
            return
        deadline = time.monotonic() + self.shutdown_timeout
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)

    def shutdown(self) -> None:
        """Stop the sender after a final bounded flush."""
        if self._worker is None:
            return
        self._stopping.set()
        self._worker.join(timeout=self.shutdown_timeout)
        self._worker = None

    def describe(self) -> str:
        """Describe the destination and its current counters."""
        if self._disabled_reason:
            return f"{type(self).__name__}(disabled: {self._disabled_reason})"
        return (
            f"{type(self).__name__}({self.url}, sent={self.sent_count}, "
            f"failed={self.failed_count}, dropped={self.dropped_count})"
        )

    # -- subclass hook -----------------------------------------------------

    def send(self, records: Sequence[dict[str, Any]]) -> None:
        """Deliver one batch. Implemented by the target-specific subclass.

        Raise to signal a failure; the base class handles the retry and the
        give-up policy. A subclass must not swallow an error, because a swallowed
        error is indistinguishable from a delivered batch.
        """
        raise NotImplementedError

    # -- worker ------------------------------------------------------------

    def _run(self) -> None:
        """Collect records into batches and send them until stopping."""
        while True:
            batch = self._collect_batch()
            if self._stopping.is_set() and not batch:
                return
            if batch:
                self._send_with_retry(batch)

    def _collect_batch(self) -> list[dict[str, Any]]:
        """Block for the first record, then gather up to a full batch."""
        try:
            first = self._queue.get(timeout=self.flush_interval)
        except queue.Empty:
            return []
        if first is None:
            return []
        batch = [first]
        deadline = time.monotonic() + self.flush_interval
        while len(batch) < self.batch_size and time.monotonic() < deadline:
            try:
                item = self._queue.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            if item is None:
                break
            batch.append(item)
        return batch

    def _send_with_retry(self, batch: list[dict[str, Any]]) -> None:
        """Send a batch, retrying a bounded number of times with backoff."""
        for attempt in range(self.max_retries + 1):
            try:
                self.send(batch)
            except Exception as exc:  # noqa: BLE001 - any transport failure is retryable
                self.failed_count += 1
                if attempt >= self.max_retries:
                    self._report_give_up(batch, exc)
                    return
                time.sleep(self.retry_backoff * (2**attempt))
            else:
                self.sent_count += len(batch)
                return

    def _report_give_up(self, batch: list[dict[str, Any]], exc: BaseException) -> None:
        """Count a batch as lost and say so once, through the standard library.

        The report goes to the standard logger rather than back into this sink,
        which would re-enter the queue that just failed.
        """
        self.dropped_count += len(batch)
        logging.getLogger(__name__).error(
            "external log sink dropped a batch after retries: %s", exc, exc_info=False
        )

    def _drop_oldest(self) -> None:
        """Discard the oldest queued record to make room for a new one."""
        try:
            self._queue.get_nowait()
        except queue.Empty:  # pragma: no cover - race with the sender
            return
        self.dropped_count += 1

    def encode_batch(self, records: Sequence[dict[str, Any]]) -> bytes:
        """Return the batch as a newline-delimited JSON body.

        Provided so a subclass that speaks plain HTTP does not have to re-decide
        the framing; a target with its own envelope overrides this.
        """
        return "\n".join(json.dumps(record, default=str) for record in records).encode("utf-8")


def build_external_sink(*, formatter: BaseFormatter, options: dict[str, Any]) -> ExternalSink:
    """Build the generic external sink.

    The base class is abstract at :meth:`ExternalSink.send`, so a deployment that
    selects ``external`` without registering a target gets a startup error rather
    than records that go nowhere quietly.
    """
    return ExternalSink(formatter=formatter, options=options)
