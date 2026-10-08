from __future__ import annotations

import xml.dom.minidom

from connector import ConnectorDefinition, ConnectorKind, ConnectorRegistry
from connector.destinations.http_batch import HttpBatchDestination
from connector.destinations.memory import InMemoryDestination
from connector.destinations.minio import MinioDestination
from connector.destinations.s3 import S3Destination
from connector.sources.clickhouse import ClickHouseSource
from connector.sources.confluence import ConfluenceSource
from connector.sources.gitlab import GitLabSource
from connector.sources.http_json import HttpJsonSource
from connector.sources.jira import JiraSource
from connector.sources.jsonl_file import JsonlFileSource
from connector.sources.minio import MinioSource
from connector.sources.mongodb import MongoDbSource
from connector.sources.mysql import MySqlSource
from connector.sources.outlook import OutlookSource
from connector.sources.postgres import PostgresSource
from connector.sources.s3 import S3Source
from connector.sources.sharepoint import SharePointSource
from tests.conftest import FakeSource

BUILTINS = [
    JsonlFileSource,
    HttpJsonSource,
    PostgresSource,
    MySqlSource,
    MongoDbSource,
    S3Source,
    ConfluenceSource,
    JiraSource,
    GitLabSource,
    OutlookSource,
    SharePointSource,
    ClickHouseSource,
    HttpBatchDestination,
    InMemoryDestination,
    MinioSource,
    S3Destination,
    MinioDestination,
]


def test_every_builtin_has_valid_svg_icon() -> None:
    for cls in BUILTINS:
        svg = cls.icon_svg()
        assert svg is not None, cls.name()
        assert svg.lstrip().startswith("<svg"), cls.name()
        xml.dom.minidom.parseString(svg)  # well-formed
        # generic marks follow the UI theme; brand marks carry their brand colour
        assert "currentColor" in svg or 'fill="#' in svg, cls.name()


def test_registry_icon_and_has_icon_flag() -> None:
    reg = ConnectorRegistry()
    reg.register(PostgresSource)
    reg.register(FakeSource)
    svg = reg.icon("postgres", ConnectorKind.SOURCE)
    assert svg and "<svg" in svg
    assert reg.icon("fake", ConnectorKind.SOURCE) is None
    flags = {i.name: i.has_icon for i in reg.list()}
    assert flags == {"postgres": True, "fake": False}


def test_missing_or_third_party_icon_reference() -> None:
    class Missing(FakeSource):
        definition = ConnectorDefinition(
            name="missing", display_name="M", kind=ConnectorKind.SOURCE, icon="nope.svg"
        )

    class ThirdParty(FakeSource):
        definition = ConnectorDefinition(
            name="tp", display_name="T", kind=ConnectorKind.SOURCE, icon="no_such_pkg.assets:x.svg"
        )

    class Dynamic(FakeSource):
        definition = ConnectorDefinition(name="dyn", display_name="D", kind=ConnectorKind.SOURCE)

        @classmethod
        def icon_svg(cls) -> str | None:
            return "<svg xmlns='http://www.w3.org/2000/svg'/>"

    assert Missing.icon_svg() is None
    assert ThirdParty.icon_svg() is None
    assert Dynamic.icon_svg() is not None
    reg = ConnectorRegistry()
    reg.register(Dynamic)
    assert reg.list()[0].has_icon is True


def test_icons_and_specs_are_read_once_per_class(monkeypatch) -> None:  # noqa: ANN001
    # A catalog request asks ~70 classes for their icon; the SVG is a package resource
    # that does not change while the process runs, and the JSON schema is deterministic.
    from importlib import resources

    from connector import base as module

    reads: list[str] = []
    real_files = resources.files

    def counting_files(package):  # noqa: ANN001, ANN202
        reads.append(str(package))
        return real_files(package)

    monkeypatch.setattr(module, "files", counting_files)
    module.clear_class_caches()
    first, second = PostgresSource.icon_svg(), PostgresSource.icon_svg()
    assert first == second and len(reads) == 1
    assert MinioSource.icon_svg() != first and len(reads) == 2  # a subclass has its own icon

    schema_calls = 0
    real_schema = PostgresSource.Config.model_json_schema

    def counting_schema(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        nonlocal schema_calls
        schema_calls += 1
        return real_schema(*args, **kwargs)

    monkeypatch.setattr(PostgresSource.Config, "model_json_schema", counting_schema)
    one, two = PostgresSource.spec(), PostgresSource.spec()
    assert one == two and schema_calls == 1
    two.connection_specification["properties"].clear()  # a caller's edit stays its own
    assert PostgresSource.spec().connection_specification["properties"]
