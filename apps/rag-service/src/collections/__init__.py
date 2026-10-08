"""Collections domain — collection *metadata* lifecycle.

Owns ``langchain_pg_collection`` (name, owner, connector type): list, get,
create, update, delete, permission-gated through ``src.shared.authorization``.
Chunk/embedding data behind a collection belongs to the ``documents`` domain.
"""
