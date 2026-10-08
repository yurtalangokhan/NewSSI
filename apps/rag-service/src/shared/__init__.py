"""Cross-cutting infrastructure shared by every domain.

Not a domain itself: authentication/authorization, configuration,
observability, idempotency, and the Postgres/vector-store connection
factories every domain's repository needs. A domain package
(``collections/``, ``documents/``, ``datasources/``, ``graph/``,
``retrieval/``) may depend on anything here; nothing here depends on a
domain.
"""
