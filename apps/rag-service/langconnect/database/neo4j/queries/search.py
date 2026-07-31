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
# Relationship type search
# ------------------------------------------------------------------

SEARCH_RELATIONSHIPS_BY_TYPE = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE type(r) IN $relationship_types
RETURN elementId(a) AS src_id,
       a.label AS src_label,
       a.name AS src_name,
       properties(a) AS src_props,
       elementId(b) AS tgt_id,
       b.label AS tgt_label,
       b.name AS tgt_name,
       properties(b) AS tgt_props,
       elementId(r) AS id,
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

SEARCH_SUBCLUSTERS = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $scope_label
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
ORDER BY degree DESC
WITH collect(n) AS all_nodes
UNWIND range(0, size(all_nodes)-1) AS i
WITH all_nodes[i] AS n, i
WHERE toLower(n.name) CONTAINS toLower($q)
WITH toInteger(i / $chunk_size) * $chunk_size AS offset, count(n) AS cnt
RETURN offset, cnt
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
