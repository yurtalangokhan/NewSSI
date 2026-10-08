"""Credentials stay out of the text a job stores and a status page shows."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from connector import (
    BaseSource,
    Catalog,
    CheckResult,
    ConfiguredCatalog,
    Connection,
    ConnectorDefinition,
    ConnectorKind,
    ConnectorRegistry,
    JobStatus,
    Record,
    State,
    Stream,
    SyncRunner,
    SyncState,
    redact_secrets,
    secret_field,
)
from connector.redaction import is_sensitive_key
from connector.sources.http_json import HttpJsonSource


def test_a_url_loses_its_query_string() -> None:
    text = (
        "HTTPStatusError: Client error '401 Unauthorized' for url "
        "'https://api.example.com/v1/items?api_key=qry-SECRET-456&page=2'\n"
        "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401"
    )

    cleaned = redact_secrets(text)

    assert "qry-SECRET-456" not in cleaned
    assert "'https://api.example.com/v1/items?***'" in cleaned
    # What a reader needs to act on the error is still there.
    assert cleaned.startswith("HTTPStatusError: Client error '401 Unauthorized' for url")
    assert cleaned.endswith("https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401")


def test_a_url_loses_the_password_of_its_user() -> None:
    assert (
        redact_secrets("cannot connect to postgresql://etl:hunter2@db.internal:5432/sales?ssl=1")
        == "cannot connect to postgresql://etl:***@db.internal:5432/sales?***"
    )
    # An "@" the password should have escaped does not let its tail through.
    assert redact_secrets("mongodb://app:p@ss:w0rd@mongo-1,mongo-2/db") == (
        "mongodb://app:***@mongo-1,mongo-2/db"
    )
    assert redact_secrets("see http://[::1]:8080/path and host:5432") == (
        "see http://[::1]:8080/path and host:5432"
    )


def test_configured_secret_values_are_replaced() -> None:
    text = "login failed for token tok-SECRET-789 (tok-SECRET-789-extended)"

    assert redact_secrets(text, ["tok-SECRET-789"]) == "login failed for token *** (***-extended)"
    # The longer value first, or its tail would stay readable.
    assert (
        redact_secrets(text, ["tok-SECRET-789", "tok-SECRET-789-extended"])
        == "login failed for token *** (***)"
    )


def test_values_too_short_to_be_told_from_ordinary_text_are_left() -> None:
    assert redact_secrets("database a1 on host a1", ["a1", ""]) == "database a1 on host a1"


@pytest.mark.parametrize(
    "name",
    [
        "Authorization",
        "Proxy-Authorization",
        "X-Api-Key",
        "x-goog-api-key",
        "apikey",
        "api_key",
        "key",
        "PRIVATE-TOKEN",
        "X-Auth-Token",
        "accessToken",
        "refresh_token",
        "Cookie",
        "client_secret",
        "credentials",
        "password",
        "PWD",
        "keyStorePassword",
        "KeyStoreSecret",
        "sig",
        "X-Hub-Signature",
        "Ocp-Apim-Subscription-Key",
        "spark.hadoop.fs.s3a.secret.key",
        "fs.azure.account.key.acct.dfs.core.windows.net",
        "spark.authenticate.secret",
    ],
)
def test_a_key_named_like_a_credential_is_sensitive(name: str) -> None:
    assert is_sensitive_key(name)


@pytest.mark.parametrize(
    "name",
    [
        "Accept",
        "Content-Type",
        "User-Agent",
        "X-Request-Id",
        "limit",
        "page",
        "author",
        "monkey",
        "keyboard_layout",
        "passenger",
        "spark.sql.session.timeZone",
        "ApplicationIntent",
        "Authentication",
        "MultiSubnetFailover",
        "max_execution_time",
    ],
)
def test_other_key_names_are_not(name: str) -> None:
    assert not is_sensitive_key(name)


def test_a_mapping_field_shows_its_keys_and_hides_what_credential_keys_hold() -> None:
    raw = {
        "url": "https://api.example.com/items",
        "bearer_token": "tok-SECRET-0",
        "headers": {"Accept": "application/json", "X-Api-Key": "hdr-SECRET-1"},
        "params": {"limit": 100, "api_key": "qry-SECRET-2", "page_token": ""},
        "body": {
            "filter": {"state": "open", "password": "bdy-SECRET-3"},
            "auth": {"client_id": "app", "client_secret": "bdy-SECRET-4"},
            "tokens": ["bdy-SECRET-5"],
        },
    }

    masked = HttpJsonSource.mask_config(raw)

    assert masked == {
        "url": "https://api.example.com/items",
        "bearer_token": "********",
        "headers": {"Accept": "application/json", "X-Api-Key": "********"},
        # An empty value stays empty, so "not set" can be told from "hidden".
        "params": {"limit": 100, "api_key": "********", "page_token": ""},
        # Whatever a credential key holds goes as a whole, at any depth.
        "body": {
            "filter": {"state": "open", "password": "********"},
            "auth": "********",
            "tokens": "********",
        },
    }
    assert "SECRET" not in json.dumps(masked)
    assert raw["headers"]["X-Api-Key"] == "hdr-SECRET-1", "the configuration itself is not touched"


def test_credentials_inside_mapping_fields_count_as_secrets_of_the_connector() -> None:
    source = HttpJsonSource.from_config(
        {
            "url": "https://api.example.com/items",
            "headers": {"Authorization": "Bearer hdr-SECRET-1", "Accept": "application/json"},
            "params": {"api_key": "qry-SECRET-2", "limit": 100},
            "body": {"auth": {"client_secret": "bdy-SECRET-3"}, "note": "plain"},
        }
    )

    secrets = source.secret_values()

    # A header value is quoted with its scheme or without it.
    assert {"Bearer hdr-SECRET-1", "hdr-SECRET-1", "qry-SECRET-2", "bdy-SECRET-3"} <= set(secrets)
    assert not {"application/json", "plain", "Bearer"} & set(secrets)
    text = "401: hdr-SECRET-1 refused (sent 'Authorization: Bearer hdr-SECRET-1', bdy-SECRET-3)"
    assert redact_secrets(text, secrets) == "401: *** refused (sent 'Authorization: ***', ***)"


class _LeakyConfig(BaseModel):
    token: str = secret_field()
    region: str = "eu"


class _LeakySource(BaseSource[_LeakyConfig]):
    """Fails the way an HTTP client does: by quoting the address, key included."""

    definition = ConnectorDefinition(name="leaky", display_name="L", kind=ConnectorKind.SOURCE)
    check_fails: bool = False

    async def check(self) -> CheckResult:
        if self.check_fails:
            return CheckResult(
                ok=False,
                message=f"401 for url 'https://api.example.com/me?api_key={self.config.token}'",
            )
        return CheckResult(ok=True)

    async def discover(self) -> Catalog:
        return Catalog(streams=[Stream(name="a")])

    async def read(
        self, catalog: ConfiguredCatalog, state: SyncState | None = None
    ) -> AsyncIterator[Record | State]:
        yield Record(stream="a", data={"id": 1})
        raise RuntimeError(
            f"401 for url 'https://api.example.com/items?api_key={self.config.token}' "
            f"(sent token {self.config.token}, region {self.config.region})"
        )


async def test_the_error_of_a_failed_job_carries_no_credential(
    registry: ConnectorRegistry,
) -> None:
    registry.register(_LeakySource)
    config = {"token": "tok-SECRET-789"}
    connection = Connection(
        name="c",
        source_name="leaky",
        source_config=config,
        destination_name="memory",
        destination_config={},
        catalog=ConfiguredCatalog.from_catalog(await _LeakySource.from_config(config).discover()),
    )
    assert _LeakySource.from_config(config).secret_values() == ["tok-SECRET-789"]
    runner = SyncRunner(registry)

    job = await runner.run(connection)

    assert job.status is JobStatus.FAILED
    assert job.error == (
        "RuntimeError: 401 for url 'https://api.example.com/items?***' (sent token ***, region eu)"
    )
    stored = await runner.job_store.get(job.id)
    assert stored is not None and stored.error == job.error


async def test_a_failed_check_carries_no_credential() -> None:
    # The verdict of a check is shown to people who may not see the configuration
    # (the datasource form, a sync's preflight): the address and the configured
    # secrets are masked wherever ``check()`` put them.
    source = _LeakySource.from_config({"token": "tok-SECRET-789"})
    source.check_fails = True
    result = await source.check_connection()
    assert not result.ok
    assert result.message == "401 for url 'https://api.example.com/me?***'"

    class _Raising(_LeakySource):
        async def check(self) -> CheckResult:
            raise RuntimeError(f"refused: token tok-SECRET-789 for {self.config.region}")

    result = await _Raising.from_config({"token": "tok-SECRET-789"}).check_connection()
    assert result.message == "RuntimeError: refused: token *** for eu"


async def test_http_check_failures_carry_no_credential() -> None:
    import httpx

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text=f"key {request.headers['x-api-key']} is over quota")

    cfg = HttpJsonSource.validate_config(
        {"url": "http://api.test/items?api_key=K-SECRET-1", "headers": {"X-Api-Key": "H-SECRET-2"}}
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://api.test")
    src = HttpJsonSource(cfg, client=client)
    src.retry_delay = 0
    result = await src.check()
    assert not result.ok and result.message is not None
    assert "K-SECRET-1" not in result.message and "H-SECRET-2" not in result.message
    assert "503" in result.message
