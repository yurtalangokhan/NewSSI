"""Cypher queries — Entity CRUD & index management."""

from __future__ import annotations

import re

RELATIONSHIP_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
FALLBACK_RELATIONSHIP_TYPE = "RELATED_TO"


def normalize_relationship_type(value: str | None) -> str:
    """Return a Cypher-safe relationship type.

    Relationship types cannot be parameterised in Cypher (see
    UPSERT_EDGE_TEMPLATE below), so an unrecognised value falls back to
    FALLBACK_RELATIONSHIP_TYPE rather than being embedded -- upper()/
    replace() alone is not a boundary once the value can come from
    LLM-extracted entity/relation output.
    """
    if not value:
        return FALLBACK_RELATIONSHIP_TYPE
    candidate = str(value).strip().upper().replace(" ", "_").replace("-", "_")
    if RELATIONSHIP_TYPE.match(candidate):
        return candidate
    return FALLBACK_RELATIONSHIP_TYPE


# ------------------------------------------------------------------
# Indexes
# ------------------------------------------------------------------

CREATE_COMPOSITE_INDEX = "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id, n.name)"

CREATE_COLLECTION_INDEX = "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id)"

CREATE_FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
FOR (n:Entity)
ON EACH [n.name, n.label]
OPTIONS {
    indexConfig: {
        `fulltext.analyzer`: 'standard-no-stop-words',
        `fulltext.eventually_consistent`: false
    }
}
"""

# ------------------------------------------------------------------
# Upsert
# ------------------------------------------------------------------

UPSERT_NODE = """
MERGE (n:Entity {collection_id: $cid, name: $name})
ON CREATE SET n.label = $label, n += $props, n.created_at = datetime()
ON MATCH SET n.label = $label, n += $props, n.updated_at = datetime()
RETURN elementId(n) AS eid
"""

# NOTE: rel_type is injected via f-string because Neo4j does not support
# parameterised relationship types. The caller MUST sanitise this value.
UPSERT_EDGE_TEMPLATE = """
MATCH (a:Entity {{collection_id: $cid, name: $src}})
MATCH (b:Entity {{collection_id: $cid, name: $tgt}})
MERGE (a)-[r:`{rel_type}` {{collection_id: $cid}}]->(b)
ON CREATE SET r += $props, r.created_at = datetime()
ON MATCH SET r += $props, r.updated_at = datetime()
RETURN elementId(r) AS eid
"""

# The bulk forms of the two statements above. They MERGE exactly the same
# way; the only difference is that the per-element values arrive as a list
# parameter and are expanded server-side, so a whole extracted graph costs
# a few round-trips instead of one per node and one per edge.
BULK_UPSERT_NODES = """
UNWIND $rows AS row
MERGE (n:Entity {collection_id: $cid, name: row.name})
ON CREATE SET n.label = row.label, n += row.props, n.created_at = datetime()
ON MATCH SET n.label = row.label, n += row.props, n.updated_at = datetime()
RETURN count(n) AS upserted
"""

# NOTE: as with UPSERT_EDGE_TEMPLATE, rel_type is injected rather than
# parameterised because Cypher does not accept a parameterised relationship
# type -- which is also why edges are grouped by type before being sent.
# The caller MUST pass a value through normalize_relationship_type.
#
# An edge whose endpoints do not exist matches nothing and is silently
# skipped, exactly as the single-edge form was (it logged and returned "").
BULK_UPSERT_EDGES_TEMPLATE = """
UNWIND $rows AS row
MATCH (a:Entity {{collection_id: $cid, name: row.src}})
MATCH (b:Entity {{collection_id: $cid, name: row.tgt}})
MERGE (a)-[r:`{rel_type}` {{collection_id: $cid}}]->(b)
ON CREATE SET r += row.props, r.created_at = datetime()
ON MATCH SET r += row.props, r.updated_at = datetime()
RETURN count(r) AS upserted
"""

# ------------------------------------------------------------------
# Read
# ------------------------------------------------------------------

GET_NODES = """
MATCH (n:Entity {{collection_id: $cid}})
{label_clause}
RETURN elementId(n) AS id, n.label AS label, n.name AS name,
       properties(n) AS props
ORDER BY n.name
SKIP $offset LIMIT $limit
"""

GET_EDGES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE r.collection_id = $cid OR r.collection_id IS NULL
RETURN elementId(r) AS id, elementId(a) AS src, elementId(b) AS tgt,
       type(r) AS rtype, properties(r) AS props
SKIP $offset LIMIT $limit
"""

# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

DELETE_COLLECTION_GRAPH = """
MATCH (n:Entity {collection_id: $cid})
DETACH DELETE n
RETURN count(*) AS deleted
"""

# ------------------------------------------------------------------
# Arbitrary Cypher (scoped)
# ------------------------------------------------------------------

# Parameters: query is passed verbatim; $cid is injected into params.
