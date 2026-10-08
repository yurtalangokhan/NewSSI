# Route shadowing in agent-service — resolved

A route registered after one that already matches the same URLs is never
reached: Starlette resolves in registration order and takes the **first** full
match.

The OpenAPI document is assembled the other way round — paths are merged into a
dictionary, so the **last** registration wins. That asymmetry is what made this
hard to see: the document described one handler while a different one ran.

Thirteen routes were affected. All are now reachable, and
`apps/agent-service/tests/api/test_route_shadowing.py` fails if a new one appears.

## What was wrong, and what changed

### A user-visible bug: provider reordering

`PUT /providers/{provider_id}` was registered before `PUT /providers/order`, so
reorder requests arrived at `update_provider` with `provider_id="order"` — and
failed validation, because the two endpoints take different bodies. The web app
calls this endpoint (`apps/web/src/hooks/useProviders.ts`), so provider
reordering was broken.

The literal path is now registered first.

### Redundant aliases that collapsed onto their canonical path

`_api_versioned_path` strips a leading `/api`, so a handler carrying both
`@router.get("/api/user/...")` and `@router.get("/user/...")` registered the same
path twice. Affected the session `files` and `token-count` endpoints; the
redundant decorator was removed.

`get_persona_llm_providers` and `get_persona_providers` were equivalent — same
permission, same controller call — so the duplicate was removed.

### Nine unreachable handlers in admin_mcp_route

`admin_mcp_route` was added on 2026-09-07 (commit `35b8595a`, *"mcp server adding
bug is fixed"*) but included after `mcp_server_admin_route` (`app.py:353` vs `:357`),
so nine of its ten endpoints never ran. The fix that commit was aiming for landed
in the shared service layer (`MCPToolService.set_tool_active`,
`mcp_tool_repo.set_active`), which both modules reach — which is why the bug was
observably fixed even though the new routes were inert.

The nine unreachable handlers were removed, along with `tool_router`, which had
no remaining routes. `mcp_server_admin_route` serves those endpoints and was already
doing so; every path resolves to exactly the handler it resolved to before.

`admin_mcp_route` keeps `GET /admin/mcp/server/{server_id}` — the one endpoint it
was actually serving, and the one the web admin panel calls.

## If admin_mcp_route's behaviour was the intended one

It differed from what serves today: string ids resolved through
`_resolve_provider` rather than an `int_id` path parameter, no `require_user`
dependency, and `mcp_tool:read` rather than `mcp_provider:sync` on tool
snapshots. None of that was ever live. Reinstating any of it is a deliberate
change to the admin API, not a restoration — start from `35b8595a` and include
the router *before* `mcp_server_admin_route`.

## The id space, unified

The same URL segment used to mean two different numbers. `GET` read it as
`numeric_id_for(uuid)` — a blake2b digest — while `PATCH`, `DELETE` and the
status and snapshot endpoints read it as `MCPProviderModel.int_id`, the
surrogate integer column. A client could not update what it had just read, and a
UUID failed path validation with 422 before any lookup happened.

`MCPProviderService.resolve_provider` is now the single reader: a numeric id
resolves through `int_id`, anything else through the UUID primary key. Every
provider endpoint uses it, so both forms work everywhere.

The read endpoint also used to *return* the digest as `id`. It now returns
`int_id`, matching `to_mcp_server_dto` and the id the frontend holds
(`MCPServer.id: number`), so a read hands back an id the writes accept.

`numeric_id_for` is retained for **tools**, which have no surrogate integer
column of their own.
