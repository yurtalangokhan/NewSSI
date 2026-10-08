from __future__ import annotations

from typing import TypeVar

import pytest
from pydantic import BaseModel

from connector import (
    BaseSource,
    ConfigValidationError,
    ConnectorDefinition,
    ConnectorKind,
    EmptyConfig,
    SyncMode,
    secret_field,
)
from connector.common.rest_source import RestSource
from connector.sources.http_json import HttpJsonSource
from tests.conftest import FakeSource


def test_spec_is_derived_from_config_model() -> None:
    spec = FakeSource.spec()
    assert spec.name == "fake"
    assert spec.kind is ConnectorKind.SOURCE
    assert spec.connection_specification["properties"]["rows"]["default"] == 5
    assert spec.supported_sync_modes == [SyncMode.FULL_REFRESH, SyncMode.INCREMENTAL]


def test_secret_field_marks_schema_and_masks() -> None:
    schema = HttpJsonSource.spec().connection_specification
    token = schema["properties"]["bearer_token"]
    assert token["x-secret"] is True and token["writeOnly"] is True
    assert HttpJsonSource.secret_fields() == {"bearer_token"}
    masked = HttpJsonSource.mask_config({"url": "http://x", "bearer_token": "abc"})
    assert masked == {"url": "http://x", "bearer_token": "********"}
    # empty secrets are left as-is so UIs can tell "unset" from "hidden"
    assert HttpJsonSource.mask_config({"bearer_token": None})["bearer_token"] is None


def test_mappings_that_may_carry_credentials_are_flagged_in_the_spec() -> None:
    from connector.destinations.http_batch import HttpBatchDestination
    from connector.sources.clickhouse import ClickHouseSource
    from connector.sources.mssql import MssqlSource
    from connector.sources.postgres import PostgresSource
    from connector.sources.spark import SparkSource

    schema = HttpJsonSource.spec().connection_specification
    assert schema["properties"]["headers"]["x-sensitive-keys"] is True
    assert "x-sensitive-keys" not in schema["properties"]["url"]

    assert HttpJsonSource.sensitive_mapping_fields() == {"headers", "params", "body"}
    assert MssqlSource.sensitive_mapping_fields() == {"extra_connection_params"}
    assert SparkSource.sensitive_mapping_fields() == {"session_config"}
    assert ClickHouseSource.sensitive_mapping_fields() == {"settings"}
    assert HttpBatchDestination.sensitive_mapping_fields() == {"extra_headers"}
    # A mapping from table to column names tables, not credentials.
    assert PostgresSource.sensitive_mapping_fields() == frozenset()

    # The flag changes neither the default nor what the field accepts.
    assert HttpJsonSource.from_config({"url": "http://x"}).config.headers == {}
    spark = SparkSource.spec().connection_specification["properties"]
    assert spark["session_config"]["description"].startswith("Spark / Hive session settings")


def test_config_validation_error_wraps_pydantic() -> None:
    with pytest.raises(ConfigValidationError) as exc:
        FakeSource.from_config({"rows": "not-a-number"})
    assert exc.value.name == "fake"
    assert exc.value.errors[0]["loc"] == ("rows",)


async def test_preview_reads_limited_rows() -> None:
    src = FakeSource.from_config({"rows": 50})
    rows = await src.preview("a", limit=3)
    assert [r["id"] for r in rows] == [1, 2, 3]


async def test_context_manager_closes() -> None:
    closed: list[bool] = []

    class Closing(FakeSource):
        definition = ConnectorDefinition(
            name="closing", display_name="C", kind=ConnectorKind.SOURCE
        )

        async def close(self) -> None:
            closed.append(True)

    async with Closing.from_config({}) as c:
        assert isinstance(c, BaseSource)
    assert closed == [True]


def test_spec_carries_category_and_icon() -> None:
    from connector import ConnectorCategory
    from connector.sources.postgres import PostgresSource

    spec = PostgresSource.spec()
    assert spec.category is ConnectorCategory.DATABASE
    assert spec.icon_svg and spec.icon_svg.lstrip().startswith("<svg")
    assert spec.model_dump()["category"] == "database"  # StrEnum serialises as plain string
    assert FakeSource.spec().category is ConnectorCategory.TESTING
    assert FakeSource.spec().icon_svg is None


def test_config_validation_error_never_carries_submitted_values() -> None:
    from connector.sources.gitlab import GitLabSource

    # A model-level validator failure reports the whole configuration as its input.
    with pytest.raises(ConfigValidationError) as exc:
        GitLabSource.from_config({"private_token": "glpat-SECRET-VALUE"})

    assert "group_id or project_ids" in str(exc.value)
    assert "SECRET" not in str(exc.value)
    assert "SECRET" not in repr(exc.value.errors)
    # The pydantic error prints its input too; it must not ride along as the cause.
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_a_connector_names_one_configuration_model() -> None:
    from tests.conftest import FakeConfig

    class Other(BaseModel):
        key: str = secret_field(default="k")

    # The type parameter alone is enough.
    class Derived(BaseSource[FakeConfig]):
        definition = ConnectorDefinition(name="d", display_name="D", kind=ConnectorKind.SOURCE)

    assert Derived.Config is FakeConfig

    # Saying two different things is refused when the class is created ...
    with pytest.raises(TypeError, match="parameterised with FakeConfig but sets Config = Other"):

        class Mismatch(BaseSource[FakeConfig]):
            Config = Other

    # ... also one level down, where the methods were written for the parent's model.
    with pytest.raises(TypeError, match="parameterised with FakeConfig but sets Config = Other"):

        class Swapped(FakeSource):
            Config = Other

    # Narrowing the model is not a contradiction: what the parent does with its model
    # still holds for a model derived from it.
    class Narrowed(FakeConfig):
        region: str = "eu"

    class NarrowedSource(FakeSource):
        Config = Narrowed

    assert NarrowedSource.Config is Narrowed
    assert NarrowedSource.from_config({"region": "us"}).config.region == "us"

    # ... and a class below it keeps the narrower model instead of getting FakeConfig back.
    class Below(NarrowedSource):
        pass

    assert Below.Config is Narrowed


def test_a_generic_base_leaves_the_model_to_its_subclasses() -> None:
    from tests.conftest import FakeConfig

    model = TypeVar("model", bound=BaseModel)

    class Open(BaseSource[model]):
        """Written for any model, like ``RestSource``: it names none itself."""

    assert Open.Config is EmptyConfig

    class ByParameter(Open[FakeConfig]):
        pass

    class ByAttribute(Open[model]):
        Config = FakeConfig

    assert ByParameter.Config is FakeConfig and ByAttribute.Config is FakeConfig
    # The built-in generic bases work the same way.
    assert RestSource.Config is EmptyConfig and HttpJsonSource.Config is not EmptyConfig
