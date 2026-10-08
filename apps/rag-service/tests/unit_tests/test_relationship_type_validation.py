"""Relationship types cannot be parameterised in Cypher, so upper()/
replace() alone was not a real boundary once the value could come from
LLM-extracted entity/relation output. Spec T1.
"""

import pytest
from pydantic import ValidationError

from src.graph.queries.entity import normalize_relationship_type
from src.graph.schemas import GraphBuildRequest

FALLBACK = "RELATED_TO"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("works_at", "WORKS_AT"),
        ("KNOWS", "KNOWS"),
        ("A1_B2", "A1_B2"),
        # Spaces and hyphens are word separators the same way "_" is --
        # this is what makes "works_at" above normalise at all, so a
        # space-separated value like an LLM might emit ("works at") must
        # be accepted the same way, not treated as an injection attempt.
        ("WORKS AT", "WORKS_AT"),
        ("works-at", "WORKS_AT"),
    ],
)
def test_valid_types_are_normalised(value, expected):
    assert normalize_relationship_type(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "`]-() DETACH DELETE n //",
        "1STARTS_WITH_DIGIT",
        "",
        None,
        "X" * 200,
        "tür_çğş",
    ],
)
def test_invalid_types_fall_back(value):
    assert normalize_relationship_type(value) == FALLBACK


def test_graph_build_request_accepts_well_formed_relationship_types():
    request = GraphBuildRequest(
        collection_id="00000000-0000-0000-0000-000000000000",
        relationship_types=["works_at", "KNOWS"],
    )
    assert request.relationship_types == ["works_at", "KNOWS"]


def test_graph_build_request_rejects_a_cypher_breaking_relationship_type():
    with pytest.raises(ValidationError):
        GraphBuildRequest(
            collection_id="00000000-0000-0000-0000-000000000000",
            relationship_types=["`]-() DETACH DELETE n //"],
        )
