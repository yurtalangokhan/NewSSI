"""Cypher queries — Visualization (clustering, expansion, neighborhood)."""

# ------------------------------------------------------------------
# Label-based clustering (fallback)
# ------------------------------------------------------------------

CLUSTER_BY_LABEL = """
MATCH (n:Entity {collection_id: $cid})
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
RETURN elementId(n) AS id, n.name AS name,
       n.label AS label, degree
ORDER BY degree DESC
"""

# ------------------------------------------------------------------
# GDS Louvain community detection
# ------------------------------------------------------------------

GDS_GRAPH_DROP = "CALL gds.graph.drop($graph_name, false)"

GDS_GRAPH_PROJECT = """
CALL gds.graph.project.cypher(
    $graph_name,
    'MATCH (n:Entity {collection_id: $cid}) RETURN id(n) AS id',
    'MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
     RETURN id(a) AS source, id(b) AS target',
    {parameters: {cid: $cid}}
)
"""

GDS_LOUVAIN_STREAM = """
CALL gds.louvain.stream($graph_name)
YIELD nodeId, communityId
WITH gds.util.asNode(nodeId) AS node, communityId
WHERE node.collection_id = $cid
RETURN elementId(node) AS id, node.name AS name,
       node.label AS label, communityId
"""

# ------------------------------------------------------------------
# All collection edges (for overview edge aggregation)
# ------------------------------------------------------------------

ALL_COLLECTION_EDGES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
RETURN elementId(a) AS src, elementId(b) AS tgt, type(r) AS rtype
"""

# ------------------------------------------------------------------
# Expand cluster (label drill-down)
# ------------------------------------------------------------------

EXPAND_CLUSTER_NODES = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $label
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
ORDER BY degree DESC
LIMIT $limit
RETURN elementId(n) AS id, n.label AS label,
       n.name AS name, properties(n) AS props
"""

EDGES_BETWEEN_IDS = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE elementId(a) IN $ids AND elementId(b) IN $ids
RETURN elementId(r) AS id, elementId(a) AS src,
       elementId(b) AS tgt, type(r) AS rtype,
       properties(r) AS props
LIMIT $elimit
"""

# ------------------------------------------------------------------
# Sub-cluster slice (offset-based)
# ------------------------------------------------------------------

EXPAND_CLUSTER_SLICE = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $label
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
ORDER BY degree DESC
SKIP $skip
LIMIT $limit
RETURN elementId(n) AS id, n.label AS label,
       n.name AS name, properties(n) AS props
"""

# ------------------------------------------------------------------
# Neighborhood (ego-graph)
# ------------------------------------------------------------------

# depth is injected via f-string (integer, safe).
NEIGHBORHOOD_TEMPLATE = """
MATCH (center:Entity {{collection_id: $cid}})
WHERE elementId(center) = $node_id
OPTIONAL MATCH path = (center)-[*1..{depth}]-(neighbor:Entity {{collection_id: $cid}})
WITH center, collect(DISTINCT neighbor) AS neighbors
UNWIND ([center] + neighbors) AS n
WITH DISTINCT n
RETURN elementId(n) AS id, n.label AS label,
       n.name AS name, properties(n) AS props
LIMIT $limit
"""

# ------------------------------------------------------------------
# Important nodes (degree centrality)
# ------------------------------------------------------------------

IMPORTANT_NODES = """
MATCH (n:Entity {collection_id: $cid})
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
ORDER BY degree DESC
LIMIT $limit
RETURN elementId(n) AS id, n.label AS label,
       n.name AS name, properties(n) AS props, degree
"""

# Full-mode edges between important nodes
EDGES_BETWEEN_IDS_FULL = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE elementId(a) IN $ids AND elementId(b) IN $ids
RETURN elementId(r) AS id, elementId(a) AS src,
       elementId(b) AS tgt, type(r) AS rtype,
       properties(r) AS props
LIMIT $limit
"""

# ------------------------------------------------------------------
# Label metadata (rel types + neighbor labels)
# ------------------------------------------------------------------

LABEL_RELATIONSHIP_TYPES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE a.label = $label AND b.label = $label
RETURN type(r) AS rtype, count(r) AS cnt
"""

LABEL_NEIGHBOR_LABELS = """
MATCH (a:Entity {collection_id: $cid})-[]-(b:Entity {collection_id: $cid})
WHERE a.label = $label
RETURN b.label AS blabel, count(DISTINCT b) AS cnt
"""

TOP_ENTITY_NAMES_BY_DEGREE = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $label
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
ORDER BY degree DESC
LIMIT $limit
RETURN n.name AS name
"""

COUNT_LABEL_NODES = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $label
RETURN count(n) AS cnt
"""

COUNT_LABEL_EDGES = """
MATCH (a:Entity {collection_id: $cid})-[r]->(b:Entity {collection_id: $cid})
WHERE a.label = $label AND b.label = $label
RETURN count(r) AS cnt
"""

CHUNKED_INTERNAL_REL_TYPES = """
MATCH (n:Entity {collection_id: $cid})
WHERE n.label = $label
OPTIONAL MATCH (n)-[r_deg]-()
WITH n, count(r_deg) AS degree
ORDER BY degree DESC
WITH collect(n) AS all_nodes
WITH all_nodes, range(0, size(all_nodes)-1, $chunk_size) AS offsets
UNWIND offsets AS offset
WITH all_nodes[offset..offset + $chunk_size] AS chunk_nodes, offset
UNWIND chunk_nodes AS a
MATCH (a)-[r]->(b:Entity {collection_id: $cid})
WHERE b.label = $label
WITH offset, type(r) AS rtype, count(r) AS cnt
RETURN offset, rtype, cnt
"""
