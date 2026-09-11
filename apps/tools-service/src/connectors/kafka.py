"""Bounded, non-committing reads from saved Airbyte Kafka sources."""

from __future__ import annotations

import asyncio
import json
import re
import ssl
from contextlib import suppress
from typing import Any

from aiokafka import AIOKafkaConsumer, TopicPartition

_TOPIC = re.compile(r"^[A-Za-z0-9._-]{1,249}$")
_MAX_LIMIT = 100
_MAX_VALUE_BYTES = 4096
_SUPPORTED_PROTOCOLS = {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}
_SUPPORTED_SASL = {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}


class ConnectorKafkaError(Exception):
    """Safe Kafka error which never contains broker credentials."""


def _jaas_credential(value: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", value)
    return (match.group(1) or match.group(2)) if match else None


def kafka_consumer_options(config: dict[str, Any]) -> dict[str, Any]:
    """Map the supported subset of native source-kafka configuration."""
    raw_servers = config.get("bootstrap_servers")
    if isinstance(raw_servers, str):
        servers = [item.strip() for item in raw_servers.split(",") if item.strip()]
    elif isinstance(raw_servers, list) and all(isinstance(item, str) for item in raw_servers):
        servers = raw_servers
    else:
        servers = []
    if not servers:
        raise ConnectorKafkaError("Kafka bootstrap servers are unavailable.")

    protocol_config = config.get("protocol") or {}
    if not isinstance(protocol_config, dict):
        raise ConnectorKafkaError("Kafka protocol configuration is invalid.")
    protocol = str(
        protocol_config.get("security_protocol") or config.get("security_protocol") or "PLAINTEXT"
    ).upper()
    if protocol not in _SUPPORTED_PROTOCOLS:
        raise ConnectorKafkaError("Kafka security protocol is not supported.")
    options: dict[str, Any] = {
        "bootstrap_servers": servers,
        "security_protocol": protocol,
        "group_id": None,
        "enable_auto_commit": False,
        "auto_offset_reset": "latest",
        "consumer_timeout_ms": 5000,
        "request_timeout_ms": 8000,
    }
    if protocol in {"SSL", "SASL_SSL"}:
        if any(
            protocol_config.get(key) or config.get(key)
            for key in ("ssl_truststore_location", "ssl_keystore_location", "ssl_key_password")
        ):
            raise ConnectorKafkaError("Custom Kafka key stores are not supported.")
        options["ssl_context"] = ssl.create_default_context()
    if protocol.startswith("SASL_"):
        mechanism = str(
            protocol_config.get("sasl_mechanism") or config.get("sasl_mechanism") or ""
        ).upper()
        if mechanism not in _SUPPORTED_SASL:
            raise ConnectorKafkaError("Kafka SASL mechanism is not supported.")
        jaas = protocol_config.get("sasl_jaas_config") or config.get("sasl_jaas_config")
        if not isinstance(jaas, str):
            raise ConnectorKafkaError("Kafka SASL credentials are unavailable.")
        username = _jaas_credential(jaas, "username")
        password = _jaas_credential(jaas, "password")
        if username is None or password is None:
            raise ConnectorKafkaError("Kafka SASL credentials are unavailable.")
        options.update(
            sasl_mechanism=mechanism,
            sasl_plain_username=username,
            sasl_plain_password=password,
        )
    return options


def decode_message_value(value: bytes | None) -> Any:
    if value is None:
        return None
    text = value[:_MAX_VALUE_BYTES].decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def read_kafka_connector(
    config: dict[str, Any], topic: str, limit: int
) -> list[dict[str, Any]]:
    """Read a recent sample from a manually assigned topic without committing offsets."""
    if not _TOPIC.fullmatch(topic):
        raise ConnectorKafkaError("Kafka topic name is invalid.")
    bounded_limit = min(max(limit, 1), _MAX_LIMIT)
    consumer = AIOKafkaConsumer(**kafka_consumer_options(config))
    try:
        await asyncio.wait_for(consumer.start(), timeout=8.0)
        partition_ids = await asyncio.wait_for(consumer.partitions_for_topic(topic), timeout=5.0)
        if not partition_ids:
            return []
        partitions = [TopicPartition(topic, number) for number in sorted(partition_ids)]
        consumer.assign(partitions)
        end_offsets = await asyncio.wait_for(consumer.end_offsets(partitions), timeout=5.0)
        for partition in partitions:
            consumer.seek(partition, max(0, end_offsets[partition] - bounded_limit))
        batches = await consumer.getmany(timeout_ms=5000, max_records=bounded_limit)
        rows = [
            {
                "partition": message.partition,
                "offset": message.offset,
                "timestamp": message.timestamp,
                "value": decode_message_value(message.value),
            }
            for messages in batches.values()
            for message in messages
        ]
        return sorted(rows, key=lambda row: (row["partition"], row["offset"]))[:bounded_limit]
    except ConnectorKafkaError:
        raise
    except Exception as exc:
        raise ConnectorKafkaError("Kafka connector read failed.") from exc
    finally:
        with suppress(Exception):
            await asyncio.wait_for(consumer.stop(), timeout=5.0)
