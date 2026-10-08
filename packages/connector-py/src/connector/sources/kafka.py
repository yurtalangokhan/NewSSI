"""Apache Kafka source: one stream per topic, read up to the current end of each partition.

A sync is finite. When it starts, the end offset (high-watermark) of every
partition is captured; reading stops once each partition reaches it. The next
offset to read is remembered per partition in the sync state, so the following
run continues where this one stopped. Partitions are assigned manually and no
consumer group is used, so nothing is committed to the broker and the
connector never interferes with real consumers of the topic.

Values and keys are decoded as ``json`` (falls back to text when the payload is
not valid JSON), ``text`` or ``base64``. Requires the ``kafka`` extra (aiokafka).
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import re
import ssl
import time
from collections import namedtuple
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..base import BaseSource, secret_field
from ..extras import optional_module, require_extra
from ..models import (
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorKind,
    Record,
    State,
    Stream,
    SyncMode,
    SyncState,
)

logger = logging.getLogger("connector.kafka")

Encoding = Literal["json", "text", "base64"]
ConsumerFactory = Callable[["KafkaConfig"], Any]

_TopicPartition = namedtuple("_TopicPartition", "topic partition")  # noqa: PYI024

CHECKPOINT_RECORDS = 10_000
"""Records of a topic between two mid-stream ``State`` checkpoints (incremental runs), so a
run that stops early - timeout, cancellation - resumes near where it got to."""

MESSAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "partition": {"type": "integer"},
        "offset": {"type": "integer"},
        "timestamp": {"type": "string", "format": "date-time"},
        "key": {},
        "value": {},
        "headers": {"type": "object"},
    },
}


class KafkaConfig(BaseModel):
    bootstrap_servers: str = Field(
        description="Comma-separated broker list, e.g. 'kafka-1:9092,kafka-2:9092'."
    )
    topics: list[str] | None = Field(default=None, description="Topics to read.")
    topic_pattern: str | None = Field(
        default=None, description="Regular expression on topic names; alternative to `topics`."
    )
    start_from: Literal["earliest", "latest"] = Field(
        default="earliest", description="Where the first sync of a partition starts."
    )
    value_format: Encoding = "json"
    key_format: Encoding = "text"
    security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = "PLAINTEXT"
    sasl_mechanism: Literal["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"] = "PLAIN"
    sasl_username: str | None = None
    sasl_password: str | None = secret_field(default=None)
    ssl_ca_pem: str | None = Field(
        default=None,
        description="CA certificate(s) in PEM form to trust. Default: the system trust store.",
    )
    ssl_check_hostname: bool = True
    client_id: str = "connector-py"
    max_records_per_topic: int | None = Field(
        default=None, description="Stop a topic after this many records; the rest comes next run."
    )
    max_poll_records: int = Field(default=500, ge=1, le=10_000)
    poll_timeout_ms: int = Field(default=1000, ge=100)
    idle_timeout_seconds: float = Field(
        default=15.0,
        description="Give up on partitions that deliver nothing for this long although their "
        "end was not reached (transaction markers, compaction).",
    )
    request_timeout_seconds: float = 40.0

    @model_validator(mode="after")
    def _rules(self) -> KafkaConfig:
        if not self.topics and not self.topic_pattern:
            raise ValueError("provide topics or topic_pattern")
        if self.security_protocol.startswith("SASL") and not (
            self.sasl_username and self.sasl_password
        ):
            raise ValueError("SASL security requires sasl_username and sasl_password")
        return self


def build_consumer_kwargs(config: KafkaConfig) -> dict[str, Any]:
    """Keyword arguments for ``aiokafka.AIOKafkaConsumer``."""
    kwargs: dict[str, Any] = {
        "bootstrap_servers": config.bootstrap_servers,
        "client_id": config.client_id,
        "group_id": None,
        "enable_auto_commit": False,
        "auto_offset_reset": config.start_from,
        "security_protocol": config.security_protocol,
        "request_timeout_ms": int(config.request_timeout_seconds * 1000),
        "max_poll_records": config.max_poll_records,
    }
    if config.security_protocol.startswith("SASL"):
        kwargs.update(
            sasl_mechanism=config.sasl_mechanism,
            sasl_plain_username=config.sasl_username,
            sasl_plain_password=config.sasl_password,
        )
    if config.security_protocol.endswith("SSL"):
        context = ssl.create_default_context(cadata=config.ssl_ca_pem or None)
        context.check_hostname = config.ssl_check_hostname
        kwargs["ssl_context"] = context
    return kwargs


def _default_consumer(config: KafkaConfig) -> Any:
    aiokafka = require_extra("aiokafka", extra="kafka", feature="kafka source")
    return aiokafka.AIOKafkaConsumer(**build_consumer_kwargs(config))


def _topic_partition_cls() -> Any:
    structs = optional_module("aiokafka.structs")
    return structs.TopicPartition if structs is not None else _TopicPartition


class KafkaSource(BaseSource[KafkaConfig]):
    definition = ConnectorDefinition(
        name="kafka",
        display_name="Apache Kafka",
        kind=ConnectorKind.SOURCE,
        category=ConnectorCategory.STREAMING,
        documentation_url="https://kafka.apache.org/documentation/",
        icon="kafka.svg",
        tags=frozenset({"streaming", "events", "self-hosted"}),
    )
    Config = KafkaConfig

    def __init__(self, config: KafkaConfig, consumer_factory: ConsumerFactory | None = None):
        super().__init__(config)
        self._factory = consumer_factory or _default_consumer
        self._consumer: Any | None = None

    @classmethod
    def supported_sync_modes(cls) -> list[SyncMode]:
        return [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]

    # ---- consumer -----------------------------------------------------------------

    async def _get_consumer(self) -> Any:
        if self._consumer is None:
            consumer = self._factory(self.config)
            await consumer.start()
            self._consumer = consumer
        return self._consumer

    async def close(self) -> None:
        if self._consumer is not None:
            consumer, self._consumer = self._consumer, None
            try:
                await consumer.stop()
            except asyncio.CancelledError:
                # aiokafka 0.14: a consumer that never polled cancels its own
                # coordinator task in stop() and lets the CancelledError out. Only a
                # cancellation of this task is ours to propagate.
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise

    async def _topics(self, consumer: Any) -> list[str]:
        if self.config.topics:
            return list(self.config.topics)
        pattern = re.compile(self.config.topic_pattern or "")
        available = await consumer.topics()
        return sorted(t for t in available if pattern.search(t) and not t.startswith("__"))

    # ---- connector API --------------------------------------------------------------

    async def check(self) -> CheckResult:
        try:
            consumer = await self._get_consumer()
            available = set(await consumer.topics())
            missing = [t for t in self.config.topics or [] if t not in available]
            if missing:
                return CheckResult(ok=False, message=f"topics not found: {', '.join(missing)}")
            if not self.config.topics and not await self._topics(consumer):
                return CheckResult(ok=False, message="topic_pattern matched no topic")
        except Exception as exc:  # noqa: BLE001 - reported to caller
            return CheckResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        consumer = await self._get_consumer()
        return Catalog(
            streams=[
                Stream(
                    name=topic,
                    json_schema=MESSAGE_SCHEMA,
                    supported_sync_modes=[SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL],
                    source_defined_cursor=True,
                    default_cursor_field=["offset"],
                    source_defined_primary_key=[["partition"], ["offset"]],
                )
                for topic in await self._topics(consumer)
            ]
        )

    async def read(
        self,
        catalog: ConfiguredCatalog,
        state: SyncState | None = None,
    ) -> AsyncIterator[Record | State]:
        state = state or SyncState()
        consumer = await self._get_consumer()
        tp_cls = _topic_partition_cls()
        cluster = await _all_metadata(consumer)
        for configured in catalog.streams:
            topic = configured.stream.name
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None and cluster is not None:
                partitions = cluster.partitions_for_topic(topic)
            if not partitions:
                logger.warning("kafka: topic %s has no partitions or does not exist", topic)
                continue
            tps = [tp_cls(topic, p) for p in sorted(partitions)]
            consumer.assign(tps)
            end = await consumer.end_offsets(tps)
            begin = await consumer.beginning_offsets(tps)

            incremental = configured.sync_mode is SyncMode.INCREMENTAL
            saved = (state.get(topic).get("offsets") or {}) if incremental else {}
            positions: dict[Any, int] = {}
            for tp in tps:
                start = saved.get(str(tp.partition))
                if start is None:
                    start = begin[tp] if self.config.start_from == "earliest" else end[tp]
                start = int(start)
                if start > int(end[tp]):
                    # The topic was recreated or truncated: what was read is gone, and a
                    # position past the end would never read anything again.
                    logger.warning(
                        "kafka: %s/%d: saved offset %d is past the end %d; starting over",
                        topic,
                        tp.partition,
                        start,
                        end[tp],
                    )
                    start = int(begin[tp])
                start = max(start, int(begin[tp]))  # retention may have removed old offsets
                consumer.seek(tp, start)
                positions[tp] = start

            remaining = {tp for tp in tps if positions[tp] < end[tp]}
            produced = 0
            since_checkpoint = 0
            limit = self.config.max_records_per_topic
            idle_since: float | None = None
            while remaining and (limit is None or produced < limit):
                batch = await consumer.getmany(
                    *sorted(remaining, key=lambda tp: tp.partition),  # a set has no stable order
                    timeout_ms=self.config.poll_timeout_ms,
                    max_records=self.config.max_poll_records,
                )
                if not batch:
                    # Only control records (transaction markers) may remain before the end:
                    # the consumer skips them, so its position tells whether the end was reached.
                    for tp in list(remaining):
                        if await self._fetch_position(consumer, tp) >= end[tp]:
                            positions[tp] = end[tp]
                            remaining.discard(tp)
                    if not remaining:
                        break
                    idle_since = idle_since or time.monotonic()
                    if time.monotonic() - idle_since >= self.config.idle_timeout_seconds:
                        logger.warning(
                            "kafka: %s delivered nothing for %.0fs on %s; stopping early",
                            topic,
                            self.config.idle_timeout_seconds,
                            sorted(tp.partition for tp in remaining),
                        )
                        break
                    continue
                idle_since = None
                for tp, messages in batch.items():
                    for msg in messages:
                        if msg.offset >= end[tp]:
                            # Produced after the sync started: the partition is read up to
                            # its snapshot end (a control record may sit just before it).
                            positions[tp] = end[tp]
                            break
                        yield Record(stream=topic, data=self._record(msg))
                        positions[tp] = msg.offset + 1
                        produced += 1
                        since_checkpoint += 1
                        if incremental and since_checkpoint >= CHECKPOINT_RECORDS:
                            since_checkpoint = 0
                            yield _checkpoint(topic, positions)
                        if limit is not None and produced >= limit:
                            break
                    if positions[tp] >= end[tp]:
                        remaining.discard(tp)
                    if limit is not None and produced >= limit:
                        break
            if incremental:
                yield _checkpoint(topic, positions)

    @staticmethod
    async def _fetch_position(consumer: Any, tp: Any) -> int:
        """The consumer's next offset for ``tp``; ``-1`` for a consumer that cannot tell."""
        position = getattr(consumer, "position", None)
        if position is None:
            return -1
        result = position(tp)
        if inspect.isawaitable(result):
            result = await result
        return int(result)

    def _record(self, msg: Any) -> dict[str, Any]:
        headers = {str(name): _decode(value, "text") for name, value in (msg.headers or []) if name}
        timestamp = None
        raw_timestamp = getattr(msg, "timestamp", None)
        if raw_timestamp is not None and raw_timestamp >= 0:  # -1: no timestamp recorded
            timestamp = datetime.fromtimestamp(raw_timestamp / 1000, tz=UTC).isoformat()
        return {
            "topic": msg.topic,
            "partition": msg.partition,
            "offset": msg.offset,
            "timestamp": timestamp,
            "key": _decode(msg.key, self.config.key_format),
            "value": _decode(msg.value, self.config.value_format),
            "headers": headers,
        }


def _checkpoint(topic: str, positions: dict[Any, int]) -> State:
    return State(
        stream=topic,
        data={"offsets": {str(tp.partition): offset for tp, offset in positions.items()}},
    )


def _decode(raw: bytes | None, encoding: Encoding) -> Any:
    if raw is None:
        return None
    if encoding == "base64":
        return base64.b64encode(raw).decode()
    text = raw.decode("utf-8", errors="replace")
    if encoding == "json":
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


async def _all_metadata(consumer: Any) -> Any | None:
    """A metadata snapshot of every topic, or ``None`` for a consumer without a client.

    A consumer without a subscription or group keeps no topic in its own cluster
    view (aiokafka 0.14: ``partitions_for_topic`` answers ``None`` for a populated
    topic, seen live against Kafka 4.3), and ``assign`` narrows that view to the
    assigned topic. The snapshot ``fetch_all_metadata`` returns is independent of
    the view, so ``read`` resolves partitions from it when the consumer has none.
    """
    client = getattr(consumer, "_client", None)
    fetch = getattr(client, "fetch_all_metadata", None)
    return await fetch() if fetch is not None else None
