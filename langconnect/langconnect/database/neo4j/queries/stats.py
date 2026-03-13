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
# Scoped stats (per label group)
# ------------------------------------------------------------------

LABEL_COUNTS_SCOPED = """
MATCH (a:Entity {collection_id: $cid})-[]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label
RETURN b.label AS label, count(DISTINCT b) AS cnt
"""

RELATIONSHIP_TYPE_COUNTS_SCOPED = """
MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label
RETURN type(r) AS rtype, count(r) AS cnt
"""

NODE_COUNT_SCOPED = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $scope_label
RETURN count(n) AS cnt
"""

EDGE_COUNT_SCOPED = """
MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label
RETURN count(r) AS cnt
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

# ------------------------------------------------------------------
# Cross-filtered queries: labels filtered by selected relationship types
# ------------------------------------------------------------------

LABELS_FILTERED_BY_REL_TYPES = """
MATCH (n:Entity {collection_id: $cid})-[r]-(:Entity {collection_id: $cid})
WHERE type(r) IN $rel_types
RETURN n.label AS label, count(DISTINCT n) AS cnt
ORDER BY cnt DESC, label
"""

LABELS_SCOPED_FILTERED_BY_REL_TYPES = """
MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label AND type(r) IN $rel_types
RETURN b.label AS label, count(DISTINCT b) AS cnt
ORDER BY cnt DESC, label
"""

# ------------------------------------------------------------------
# Cross-filtered queries: rel types filtered by selected labels
# ------------------------------------------------------------------

REL_TYPES_FILTERED_BY_LABELS = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE a.label IN $labels OR b.label IN $labels
RETURN type(r) AS rtype, count(*) AS cnt
ORDER BY cnt DESC, rtype
"""

REL_TYPES_SCOPED_FILTERED_BY_LABELS = """
MATCH (a:Entity {collection_id: $cid})-[r]-(b:Entity {collection_id: $cid})
WHERE a.label = $scope_label AND b.label IN $labels
RETURN type(r) AS rtype, count(r) AS cnt
ORDER BY cnt DESC, rtype
"""
