"""Translate a saved connector configuration into the tools-service read contract.

tools-service gives agents bounded, read-only access to a saved connector
(``connector_list_resources`` / ``connector_read``). It does not run the
connector: it has its own small adapter per system and expects the
configuration in the shape that adapter reads, under the adapter's type name.

Datasource configurations are stored in the connector's own shape (the
``Config`` model of the connector-py source). This module is the one place that
maps one onto the other. A translator returns ``None`` when the saved
configuration uses something the tools-service adapter cannot do (a custom CA,
temporary credentials, several roots); the connector is then reported as
unavailable for live tools instead of failing at read time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

Config = dict[str, Any]


@dataclass(frozen=True)
class ToolConnector:
    """What tools-service receives for one saved connector."""

    connector_type: str
    config: Config


def _postgres(config: Config) -> ToolConnector:
    return ToolConnector(
        "source-postgres",
        {
            "host": config.get("host"),
            "port": config.get("port", 5432),
            "username": config.get("username"),
            "password": config.get("password"),
            "database": config.get("database"),
            "ssl_mode": {"mode": "require" if config.get("ssl") else "disable"},
        },
    )


def _mysql(config: Config) -> ToolConnector:
    # The adapter negotiates TLS opportunistically ("preferred") whatever the source does.
    return ToolConnector(
        "source-mysql",
        {
            "host": config.get("host"),
            "port": config.get("port", 3306),
            "username": config.get("username"),
            "password": config.get("password"),
            "database": config.get("database"),
            "ssl_mode": {"mode": "preferred"},
        },
    )


def _mssql(config: Config) -> ToolConnector | None:
    if not config.get("username"):
        return None  # integrated authentication has no counterpart in the adapter
    if not config.get("encrypt", True):
        ssl_method = "unencrypted"
    elif config.get("trust_server_certificate"):
        ssl_method = "encrypted_trust_server_certificate"
    else:
        return None  # certificate verification is not implemented by the adapter
    return ToolConnector(
        "source-mssql",
        {
            "host": config.get("host"),
            "port": config.get("port", 1433),
            "username": config.get("username"),
            "password": config.get("password"),
            "database": config.get("database"),
            "ssl_method": {"ssl_method": ssl_method},
        },
    )


def _mongodb(config: Config) -> ToolConnector:
    return ToolConnector(
        "source-mongodb-v2",
        {"connection_string": config.get("connection_string"), "database": config.get("database")},
    )


def _search(adapter_type: str) -> Callable[[Config], ToolConnector]:
    def translate(config: Config) -> ToolConnector:
        translated: Config = {"endpoint": config.get("url")}
        if config.get("api_key"):
            translated["api_key"] = config["api_key"]
        elif config.get("username") is not None and config.get("password") is not None:
            translated["username"] = config["username"]
            translated["password"] = config["password"]
        return ToolConnector(adapter_type, translated)

    return translate


def _kafka(config: Config) -> ToolConnector | None:
    if config.get("ssl_ca_pem"):
        return None  # the adapter trusts the system store only
    protocol: Config = {"security_protocol": config.get("security_protocol", "PLAINTEXT")}
    if str(protocol["security_protocol"]).startswith("SASL"):
        username, password = config.get("sasl_username"), config.get("sasl_password")
        if not username or not password or '"' in username or '"' in password:
            return None  # the adapter reads credentials from a quoted JAAS string
        protocol["sasl_mechanism"] = config.get("sasl_mechanism", "PLAIN")
        protocol["sasl_jaas_config"] = f'username="{username}" password="{password}"'
    return ToolConnector(
        "source-kafka",
        {"bootstrap_servers": config.get("bootstrap_servers"), "protocol": protocol},
    )


def _object_store_streams(config: Config) -> list[Config]:
    prefix = str(config.get("prefix") or "").strip("/")
    streams = []
    for stream in config.get("streams") or [{"name": "files", "glob": "**"}]:
        pattern = str(stream.get("glob") or "**").lstrip("/")
        streams.append({"name": stream.get("name"), "globs": [f"{prefix}/{pattern}" if prefix else pattern]})
    return streams


def _s3(config: Config) -> ToolConnector | None:
    if config.get("aws_session_token") or not config.get("aws_access_key_id"):
        return None  # only long-lived access keys are supported by the adapter
    return ToolConnector(
        "source-s3",
        {
            "bucket": config.get("bucket"),
            "aws_access_key_id": config.get("aws_access_key_id"),
            "aws_secret_access_key": config.get("aws_secret_access_key"),
            "region_name": config.get("region"),
            "endpoint": config.get("endpoint_url"),
            "streams": _object_store_streams(config),
        },
    )


def _minio(config: Config) -> ToolConnector:
    endpoint = str(config.get("endpoint") or "")
    if endpoint and "://" not in endpoint:
        endpoint = f"{'https' if config.get('secure') else 'http'}://{endpoint}"
    return ToolConnector(
        "source-s3",
        {
            "bucket": config.get("bucket"),
            "aws_access_key_id": config.get("access_key"),
            "aws_secret_access_key": config.get("secret_key"),
            "region_name": config.get("region"),
            "endpoint": endpoint,
            "streams": _object_store_streams(config),
        },
    )


def _sftp(config: Config) -> ToolConnector | None:
    paths = config.get("paths") or ["/"]
    if len(paths) != 1:
        return None  # the adapter reads below a single root folder
    translated: Config = {
        "host": config.get("host"),
        "port": config.get("port", 22),
        "username": config.get("username"),
        "folder_path": paths[0],
        "streams": [{"name": "files", "globs": [str(config.get("glob") or "**/*").lstrip("/")]}],
    }
    for key in ("password", "private_key", "private_key_passphrase"):
        if config.get(key):
            translated[key] = config[key]
    return ToolConnector("source-sftp-bulk", translated)


def _http_json(config: Config) -> ToolConnector | None:
    parsed = urlsplit(str(config.get("url") or ""))
    if config.get("method", "GET") != "GET" or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    headers = {str(k): str(v) for k, v in (config.get("headers") or {}).items()}
    if config.get("bearer_token"):
        headers["Authorization"] = f"Bearer {config['bearer_token']}"
    path = parsed.path or "/"
    return ToolConnector(
        "source-http-request",
        {
            "base_url": f"{parsed.scheme}://{parsed.netloc}",
            "resources": {config.get("stream_name") or "records": f"{path}?{parsed.query}" if parsed.query else path},
            "headers": headers,
        },
    )


_TRANSLATORS: dict[str, Callable[[Config], ToolConnector | None]] = {
    "postgres": _postgres,
    "mysql": _mysql,
    "mssql": _mssql,
    "mongodb": _mongodb,
    "elasticsearch": _search("source-elasticsearch"),
    "opensearch": _search("source-opensearch"),
    "kafka": _kafka,
    "s3": _s3,
    "minio": _minio,
    "sftp": _sftp,
    "http_json": _http_json,
}

#: Connectors tools-service has a live-read adapter for.
SUPPORTED_CONNECTORS = frozenset(_TRANSLATORS)

#: Connectors that are always readable once configured; the others depend on
#: how they are configured and need the configuration to decide.
ALWAYS_AVAILABLE = frozenset({"postgres", "mysql", "mongodb", "elasticsearch", "opensearch", "minio"})


def to_tool_connector(connector_name: str, config: Config) -> ToolConnector | None:
    """The tools-service view of a saved configuration, or ``None`` when unsupported."""
    translate = _TRANSLATORS.get(connector_name)
    return translate(config) if translate else None
