"""The Elasticsearch destination: records into an ELK stack over the bulk API.

This is the concrete log platform the package ships, built on the generic
:class:`~observability.sinks.external.ExternalSink` base — which is why it is
short. The base already owns the queue, the batching, the retries, and the
drop policy; this class only speaks Elasticsearch's wire format.

Records are delivered through the ``_bulk`` API as newline-delimited JSON: one
action line and one document line per record. The target index defaults to
``logs-<service>`` per record, so each service lands in its own index and an
index mapping written against the field contract applies service-wide. A fixed
index name can be set with the ``index`` option.

Delivery is at-least-once: a batch whose bulk response reports item failures is
retried whole by the base class, so a partially applied batch can duplicate
records. For logs that is the right trade — losing an error record during an
incident is worse than indexing it twice.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from .external import ExternalSink

DEFAULT_TIMEOUT = 10.0


class ElasticsearchSink(ExternalSink):
    """Deliver batches to Elasticsearch through the ``_bulk`` API."""

    def __init__(self, *, formatter: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(formatter=formatter, options=options)
        options = options or {}
        self.index = str(options["index"]) if options.get("index") else None
        self.timeout = float(options.get("timeout", DEFAULT_TIMEOUT))

    def send(self, records: Sequence[dict[str, Any]]) -> None:
        """Deliver one batch as a bulk request.

        Raises on any transport or item failure, which is what hands the batch
        back to the base class's retry policy; a swallowed failure here would be
        indistinguishable from a delivered one.
        """
        body = self.encode_bulk(records)
        response_body = self._post(body)
        failed = self._failed_items(response_body)
        if failed:
            raise RuntimeError(f"elasticsearch rejected {failed} of {len(records)} records")

    def encode_bulk(self, records: Sequence[dict[str, Any]]) -> bytes:
        """Return the batch as an ndjson bulk body.

        Each record carries its own action line, so a mixed batch can land in
        per-service indexes without being split first.
        """
        lines: list[str] = []
        for record in records:
            action = {"index": {"_index": self._index_for(record)}}
            lines.append(json.dumps(action, separators=(",", ":")))
            lines.append(json.dumps(record, separators=(",", ":"), default=str))
        return ("\n".join(lines) + "\n").encode("utf-8")

    def _index_for(self, record: dict[str, Any]) -> str:
        """The index one record lands in: configured, else per-service."""
        if self.index:
            return self.index
        return f"logs-{record.get('service') or 'unknown'}"

    def _post(self, body: bytes) -> dict[str, Any]:
        """POST the bulk body and return the parsed response.

        Split out so a test can capture the wire format without a server.
        """
        request = urllib.request.Request(
            f"{self.url.rstrip('/')}/_bulk",
            data=body,
            headers={**self.headers, "Content-Type": "application/x-ndjson"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # The response body often carries the per-item errors; surface it so
            # the retry report says why the platform refused the batch.
            detail = exc.read().decode("utf-8", errors="replace")[:500]

            raise RuntimeError(
                f"elasticsearch bulk request failed with {exc.code}: {detail}"
            ) from exc

    def _failed_items(self, response_body: dict[str, Any]) -> int:
        """Count the items a bulk response reports as failed."""
        if not response_body.get("errors"):
            return 0
        return sum(
            1
            for item in response_body.get("items", [])
            for result in item.values()
            if result.get("status", 0) >= 300
        )

    def describe(self) -> str:
        """Describe the destination, including the index policy."""
        base = super().describe()
        if self.index:
            return base.replace(self.url, f"{self.url} index={self.index}")
        return base


def build_elasticsearch_sink(*, formatter: Any, options: dict[str, Any]) -> ElasticsearchSink:
    """Build the Elasticsearch destination from configuration options."""
    return ElasticsearchSink(formatter=formatter, options=options)
