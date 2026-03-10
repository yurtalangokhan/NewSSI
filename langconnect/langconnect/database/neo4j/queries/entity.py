"""Cypher queries — Entity CRUD & index management."""

# ------------------------------------------------------------------
# Indexes
# ------------------------------------------------------------------

CREATE_COMPOSITE_INDEX = (
    "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id, n.name)"
)

CREATE_COLLECTION_INDEX = (
    "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.collection_id)"
)

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
