"""Canonical composite roles that grant admin-area access.

`system-admin` and `enterprise-admin` are the two canonical composite
roles (see migration 0029_reconcile_canonical_composite_roles) that should
unlock the admin UI and coarse "is this user an admin" checks.

This is intentionally a static set of role *names* rather than a mutable
per-row database flag (the old `composite_roles.is_admin` column): the
canonical role catalog already treats these two roles as the fixed,
builtin admin tier, so checking membership by name keeps a single source
of truth instead of a column that can silently drift out of sync with it.

Do NOT use permission-string overlap (e.g. "does this user have any one
permission that some admin page happens to require") to answer "is this
user an admin" - end users are legitimately granted plenty of read-only
permissions (datasource:read, graph:read, agent:list, provider:read, ...)
for ordinary in-app features, and those exact permission strings are also
used to gate individual admin pages. Reusing that overlap as a coarse
admin flag is what let end users see the admin panel; the coarse check
must come from the user's actual composite role assignment instead.
"""

ADMIN_COMPOSITE_ROLE_NAMES: frozenset[str] = frozenset({"system-admin", "enterprise-admin"})


def is_admin_role_name(name: str | None) -> bool:
    """Whether a composite role name grants admin-area access."""
    return bool(name) and name in ADMIN_COMPOSITE_ROLE_NAMES
