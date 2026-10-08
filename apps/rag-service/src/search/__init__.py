"""Search domain — the knowledge search page's multi-collection search.

Fans one query out over every collection the caller may read, runs vector
and/or graph retrieval per collection through the ``retrieval`` contract,
fuses the ranked lists, and returns hits, a merged subgraph and facets.
"""
