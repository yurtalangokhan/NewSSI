"""``sanitize_neo4j_value`` is the single canonical Neo4j-value-to-JSON conversion.

It used to exist twice: ``Neo4jRepository._sanitize_props`` (node/edge
properties) converted Neo4j temporal types properly but never recursed into
a plain nested dict, while ``api/graph.py``'s ``_serialize_neo4j_value``
(raw admin Cypher results) recursed into everything but fell back to
``str()`` for a Neo4j temporal value instead of converting it -- so the
same timestamp came back in a different format depending on which endpoint
returned it. This is the merged, single implementation both now share.
"""

from datetime import UTC, date, datetime, time, timedelta

from neo4j.time import Date as Neo4jDate
from neo4j.time import DateTime as Neo4jDateTime
from neo4j.time import Duration as Neo4jDuration
from neo4j.time import Time as Neo4jTime

from src.graph.repositories.base import (
    Neo4jRepository,
    sanitize_neo4j_value,
)


def test_scalars_pass_through_unchanged():
    assert sanitize_neo4j_value(None) is None
    assert sanitize_neo4j_value("x") == "x"
    assert sanitize_neo4j_value(42) == 42
    assert sanitize_neo4j_value(3.14) == 3.14
    assert sanitize_neo4j_value(True) is True


def test_neo4j_datetime_converts_to_native_isoformat():
    value = Neo4jDateTime(2024, 1, 15, 10, 30, 0)
    assert sanitize_neo4j_value(value) == "2024-01-15T10:30:00"


def test_neo4j_date_converts_to_native_isoformat():
    value = Neo4jDate(2024, 1, 15)
    assert sanitize_neo4j_value(value) == "2024-01-15"


def test_neo4j_time_converts_to_native_isoformat():
    value = Neo4jTime(10, 30, 0)
    assert sanitize_neo4j_value(value) == "10:30:00"


def test_neo4j_duration_converts_to_string():
    value = Neo4jDuration(days=1, hours=2)
    assert sanitize_neo4j_value(value) == "P1DT2H"


def test_stdlib_temporal_types_convert_via_isoformat():
    dt = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
    assert sanitize_neo4j_value(dt) == dt.isoformat()
    assert sanitize_neo4j_value(date(2024, 1, 15)) == "2024-01-15"
    assert sanitize_neo4j_value(time(10, 30)) == "10:30:00"


def test_stdlib_timedelta_converts_to_string():
    assert sanitize_neo4j_value(timedelta(days=1)) == str(timedelta(days=1))


def test_list_recurses_into_temporal_items():
    value = [Neo4jDate(2024, 1, 1), "plain", 5]
    assert sanitize_neo4j_value(value) == ["2024-01-01", "plain", 5]


def test_tuple_recurses_and_becomes_a_list():
    value = (Neo4jDate(2024, 1, 1), "plain")
    assert sanitize_neo4j_value(value) == ["2024-01-01", "plain"]


def test_plain_nested_dict_recurses_too():
    """The bug in the old node/edge-properties sanitizer: a temporal value
    nested inside a plain dict (not inside a list) was left unconverted.
    """
    value = {"outer": {"when": Neo4jDate(2024, 1, 1), "label": "x"}}
    assert sanitize_neo4j_value(value) == {"outer": {"when": "2024-01-01", "label": "x"}}


def test_dict_nested_inside_a_list_recurses():
    value = [{"when": Neo4jDate(2024, 1, 1)}]
    assert sanitize_neo4j_value(value) == [{"when": "2024-01-01"}]


def test_unrecognised_type_falls_back_to_str():
    class Weird:
        def __str__(self) -> str:
            return "weird-value"

    assert sanitize_neo4j_value(Weird()) == "weird-value"


def test_neo4j_repository_sanitize_props_delegates_to_the_shared_function():
    props = {"created": Neo4jDate(2024, 1, 1), "nested": {"when": Neo4jDate(2024, 6, 1)}}
    assert Neo4jRepository._sanitize_props(props) == {
        "created": "2024-01-01",
        "nested": {"when": "2024-06-01"},
    }
