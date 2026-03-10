"""Cypher queries — Graph statistics."""

# ------------------------------------------------------------------
# Collection list
# ------------------------------------------------------------------

LIST_GRAPH_COLLECTION_IDS = (
    "MATCH (n:Entity) RETURN DISTINCT n.collection_id AS cid"
)

# ------------------------------------------------------------------
# Stats (per collection)
# ------------------------------------------------------------------

LABEL_COUNTS = """
MATCH (n:Entity {collection_id: $cid})
RETURN n.label AS label, count(*) AS cnt
"""

RELATIONSHIP_TYPE_COUNTS = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
RETURN type(r) AS rtype, count(*) AS cnt
"""

# ------------------------------------------------------------------
# Paginated label / relationship-type queries
# ------------------------------------------------------------------

LABELS_PAGINATED_SCOPED = """
MATCH (a:Entity {collection_id: $cid})-[]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label
RETURN b.label AS label, count(DISTINCT b) AS cnt
ORDER BY cnt DESC, label
"""

LABELS_PAGINATED_UNSCOPED = """
MATCH (n:Entity {collection_id: $cid})
RETURN n.label AS label, count(*) AS cnt
ORDER BY cnt DESC, label
"""

RELATIONSHIP_TYPES_PAGINATED_SCOPED = """
MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label
RETURN type(r) AS rtype, count(r) AS cnt
ORDER BY cnt DESC, rtype
"""

RELATIONSHIP_TYPES_PAGINATED_UNSCOPED = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
RETURN type(r) AS rtype, count(*) AS cnt
ORDER BY cnt DESC, rtype
"""
