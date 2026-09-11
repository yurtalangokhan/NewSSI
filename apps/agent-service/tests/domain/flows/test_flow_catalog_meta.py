"""Flow metadata carried on the persona payloads.

The list page renders a version chip, a "has draft" dot and a timestamp
per flow card. Fetching those per card would be one request per row, so
they ride along on the catalog response — and the catalog already batches
its definition lookup, so the summaries are batched the same way.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from controller.persona_controller import flow_meta_fields
from repository.flow_version_repository import FlowSummary


class _Definition:
    def __init__(self, definition_id, graph_schema="flow"):
        self.id = definition_id
        self.graph_schema = graph_schema


def test_meta_fields_from_summary():
    definition_id = uuid4()
    updated = datetime(2026, 9, 4, 10, 30)

    fields = flow_meta_fields(
        _Definition(definition_id),
        {definition_id: FlowSummary(published_version_no=3, has_draft=True, updated_at=updated)},
    )

    assert fields == {
        "flow_published_version_no": 3,
        "flow_has_draft": True,
        "flow_updated_at": updated.isoformat(),
    }


def test_meta_fields_default_when_summary_missing():
    fields = flow_meta_fields(_Definition(uuid4()), {})

    assert fields == {
        "flow_published_version_no": None,
        "flow_has_draft": False,
        "flow_updated_at": None,
    }


def test_meta_fields_empty_for_non_flow_definition():
    definition_id = uuid4()
    assert flow_meta_fields(_Definition(definition_id, graph_schema="zero_shot"), {}) == {}


def test_meta_fields_empty_without_definition():
    assert flow_meta_fields(None, {}) == {}
