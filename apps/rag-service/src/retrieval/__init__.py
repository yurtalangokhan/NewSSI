"""Retrieval domain — unified agent-facing search.

A single internal contract (``retrieval.contract``) that fuses vector
search (``documents`` domain) and graph search (``graph`` domain) behind
one endpoint for tools-service. Additive: the public document/graph search
routes in their own domains remain the UI contract.
"""
