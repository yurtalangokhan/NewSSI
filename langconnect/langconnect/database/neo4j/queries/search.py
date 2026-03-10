"""Cypher queries — Search (fulltext BM25, CONTAINS, entity clusters, context)."""

# ------------------------------------------------------------------
# BM25 fulltext search
# ------------------------------------------------------------------

BM25_SEARCH = """
CALL db.index.fulltext.queryNodes(
    'entity_fulltext', $lucene_query, {limit: $max_results}
) YIELD node, score
WHERE node.collection_id = $cid
RETURN elementId(node) AS id,
       node.label AS label,
       node.name  AS name,
       properties(node) AS props,
       score
ORDER BY score DESC
LIMIT $limit
"""

# ------------------------------------------------------------------
# Case-insensitive CONTAINS search
# ------------------------------------------------------------------

SEARCH_ENTITIES_CONTAINS = """
MATCH (n:Entity {collection_id: $cid})
WHERE toLower(n.name) CONTAINS toLower($q)
RETURN elementId(n) AS id, n.label AS label, n.name AS name,
       properties(n) AS props
LIMIT $limit
"""

SEARCH_NEIGHBORHOOD_EDGES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE elementId(a) IN $ids OR elementId(b) IN $ids
RETURN elementId(r) AS id, elementId(a) AS src, elementId(b) AS tgt,
       type(r) AS rtype, properties(r) AS props
LIMIT 100
"""

FETCH_NODES_BY_IDS = """
MATCH (n:Entity {collection_id: $cid})
WHERE elementId(n) IN $ids
RETURN elementId(n) AS id, n.label AS label, n.name AS name,
       properties(n) AS props
"""

# ------------------------------------------------------------------
# Fetch edges for named nodes
# ------------------------------------------------------------------

FETCH_EDGES_FOR_NAMES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE a.name IN $names OR b.name IN $names
RETURN elementId(r) AS id,
       elementId(a) AS src,
       elementId(b) AS tgt,
       type(r) AS rtype,
       properties(r) AS props
LIMIT $limit
"""

# ------------------------------------------------------------------
# Entity cluster search (label → count)
# ------------------------------------------------------------------

SEARCH_ENTITY_CLUSTERS = """
MATCH (n:Entity {collection_id: $cid})
WHERE toLower(n.name) CONTAINS toLower($q)
RETURN n.label AS label, count(n) AS cnt
"""

# ------------------------------------------------------------------
# Entity context for RAG
# ------------------------------------------------------------------

# depth is injected via f-string (integer, safe).
ENTITY_CONTEXT_TEMPLATE = """
MATCH (n:Entity {{collection_id: $cid, name: $name}})
OPTIONAL MATCH path = (n)-[*1..{depth}]-(m:Entity {{collection_id: $cid}})
UNWIND relationships(path) AS r
WITH DISTINCT startNode(r) AS s, type(r) AS rtype, endNode(r) AS t
RETURN s.name AS src, rtype, t.name AS tgt
LIMIT 50
"""

ENTITY_CONTEXT_FOCUSED = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE a.name IN $names OR b.name IN $names
RETURN a.name AS src, type(r) AS rtype, b.name AS tgt
LIMIT $max_total
"""
