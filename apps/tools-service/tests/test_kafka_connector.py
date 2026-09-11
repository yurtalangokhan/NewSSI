from __future__ import annotations

import pytest

from src.connectors.kafka import ConnectorKafkaError, read_kafka_connector


class TopicPartition:
    def __init__(self, topic: str, partition: int):
        self.topic = topic
        self.partition = partition

    def __hash__(self):
        return hash((self.topic, self.partition))

    def __eq__(self, other):
        return (self.topic, self.partition) == (other.topic, other.partition)


class Message:
    def __init__(self, partition: int, offset: int, value: bytes):
        self.partition = partition
        self.offset = offset
        self.value = value
        self.key = None
        self.timestamp = 1_700_000_000_000


@pytest.mark.asyncio
async def test_reads_latest_bounded_sample_without_group_or_commits(monkeypatch):
    calls = {}

    class Consumer:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        async def start(self):
            calls["started"] = True

        async def stop(self):
            calls["stopped"] = True

        async def partitions_for_topic(self, topic):
            calls["topic"] = topic
            return {0, 1}

        def assign(self, partitions):
            calls["assigned"] = partitions

        async def end_offsets(self, partitions):
            return {partitions[0]: 10, partitions[1]: 3}

        def seek(self, partition, offset):
            calls.setdefault("seeks", []).append((partition.partition, offset))

        async def getmany(self, **kwargs):
            calls["getmany"] = kwargs
            p0, p1 = calls["assigned"]
            return {
                p0: [Message(0, 8, b'{"id": 8}'), Message(0, 9, b'{"id": 9}')],
                p1: [Message(1, 2, b"plain")],
            }

    monkeypatch.setattr("src.connectors.kafka.AIOKafkaConsumer", Consumer)
    monkeypatch.setattr("src.connectors.kafka.TopicPartition", TopicPartition)

    rows = await read_kafka_connector(
        {
            "bootstrap_servers": "kafka-1:9092,kafka-2:9092",
            "protocol": {"security_protocol": "PLAINTEXT"},
        },
        "orders",
        4,
    )

    assert calls["kwargs"]["bootstrap_servers"] == ["kafka-1:9092", "kafka-2:9092"]
    assert calls["kwargs"]["enable_auto_commit"] is False
    assert calls["kwargs"]["group_id"] is None
    assert calls["seeks"] == [(0, 6), (1, 0)]
    assert calls["getmany"] == {"timeout_ms": 5000, "max_records": 4}
    assert rows == [
        {"partition": 0, "offset": 8, "timestamp": 1_700_000_000_000, "value": {"id": 8}},
        {"partition": 0, "offset": 9, "timestamp": 1_700_000_000_000, "value": {"id": 9}},
        {"partition": 1, "offset": 2, "timestamp": 1_700_000_000_000, "value": "plain"},
    ]
    assert calls["stopped"] is True


@pytest.mark.asyncio
async def test_empty_topic_returns_empty_and_stops(monkeypatch):
    calls = {}

    class Consumer:
        def __init__(self, **_kwargs):
            pass

        async def start(self):
            pass

        async def stop(self):
            calls["stopped"] = True

        async def partitions_for_topic(self, _topic):
            return set()

    monkeypatch.setattr("src.connectors.kafka.AIOKafkaConsumer", Consumer)

    assert await read_kafka_connector(
        {"bootstrap_servers": "kafka:9092", "protocol": {"security_protocol": "PLAINTEXT"}},
        "empty",
        10,
    ) == []
    assert calls["stopped"] is True


@pytest.mark.asyncio
async def test_start_timeout_still_stops_consumer(monkeypatch):
    calls = {}

    class Consumer:
        def __init__(self, **_kwargs):
            pass

        async def start(self):
            raise TimeoutError

        async def stop(self):
            calls["stopped"] = True

    monkeypatch.setattr("src.connectors.kafka.AIOKafkaConsumer", Consumer)

    with pytest.raises(ConnectorKafkaError):
        await read_kafka_connector(
            {
                "bootstrap_servers": "kafka:9092",
                "protocol": {"security_protocol": "PLAINTEXT"},
            },
            "orders",
            10,
        )
    assert calls["stopped"] is True


def test_sasl_config_is_mapped_and_unsupported_auth_fails_closed():
    from src.connectors.kafka import kafka_consumer_options

    options = kafka_consumer_options(
        {
            "bootstrap_servers": "kafka:9093",
            "protocol": {
                "security_protocol": "SASL_SSL",
                "sasl_mechanism": "SCRAM-SHA-256",
                "sasl_jaas_config": (
                    'org.apache.kafka.common.security.scram.ScramLoginModule required '
                    'username="reader" password="secret";'
                ),
            },
        }
    )
    assert options["security_protocol"] == "SASL_SSL"
    assert options["sasl_mechanism"] == "SCRAM-SHA-256"
    assert options["sasl_plain_username"] == "reader"
    assert options["sasl_plain_password"] == "secret"
    assert options["ssl_context"].check_hostname is True

    with pytest.raises(ConnectorKafkaError):
        kafka_consumer_options(
            {
                "bootstrap_servers": "kafka:9093",
                "protocol": {
                    "security_protocol": "SASL_SSL",
                    "sasl_mechanism": "OAUTHBEARER",
                },
            }
        )


def test_message_values_are_json_when_possible_and_never_unbounded():
    from src.connectors.kafka import decode_message_value

    assert decode_message_value(b'{"ok": true}') == {"ok": True}
    assert decode_message_value(b"hello") == "hello"
    assert len(decode_message_value(b"x" * 10_000)) == 4096
