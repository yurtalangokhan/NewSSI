# Shared Runtime Env Design

## Goal

All runtime code must read environment-backed configuration through a central
module, never through direct `os.environ`, `os.getenv`, or ad hoc
`process.env.NAME || fallback` expressions. Missing required runtime values
must fail with a clear error at settings construction or first access.

## Scope

This design covers:

- `apps/agent-service`
- `apps/rag-service`
- `apps/user-service`
- `apps/tools-service`
- server-side web route configuration in `apps/web`

It excludes:

- tests and fixtures
- generated files and lock files
- docs, placeholder examples, and user-facing external documentation links
- literals that are domain constants rather than deployment configuration

## Architecture

Each service owns one runtime env module with the same shape:

- `Settings`: typed config object
- `get_settings()`: cached accessor
- `settings`: module-level singleton where the service already uses that style
- `require_env(name, value)`: shared local helper semantics for required values

Python services keep the module inside their existing service boundary:

- agent-service: `src/core/settings.py` remains canonical; `src/core/env.py`
  becomes a compatibility wrapper or is retired gradually.
- user-service: `src/config.py` remains canonical; `src/core/env.py` becomes a
  compatibility wrapper or is retired gradually.
- rag-service: `langconnect/config.py` remains canonical and exposes a
  `Settings` object while preserving existing module constants during migration.
- tools-service: add `src/core/settings.py` and route all env access through it.

Web server code gets one server-only module:

- `src/lib/env.server.ts`

This module exports required URL helpers such as `getInternalUrl()`,
`getAgentServiceUrl()`, `getRagServiceUrl()`, `getUserServiceUrl()`, and
`getToolsServiceUrl()`.

## Required vs Optional Values

Runtime required values follow `scripts/env_manager.py` specs. If a variable is
`required=True` and does not allow empty values there, application code should
not invent a fallback.

Examples of required values:

- service-to-service URLs
- database host, port, user, password, and database name for DB-backed services
- auth secrets and internal service tokens
- Keycloak client secrets when Keycloak is enabled

Examples of optional values:

- feature flags
- tracing flags
- disabled-provider credentials
- dev-only debug cookies
- optional LDAP fields when LDAP is disabled

Development defaults remain in `scripts/env_manager.py` and generated `.env`
files, not scattered across runtime modules.

## Data Flow

1. `make env-init` creates app env files from `scripts/env_manager.py`.
2. `make env-check` confirms required values exist and are non-empty.
3. Service startup imports its central settings module.
4. Runtime modules consume the central settings object.
5. If a required value is absent, the central settings module raises an explicit
   error naming the missing variable.

## Error Handling

Required config failures should use `ValueError` in Python and `Error` in
TypeScript with messages like:

```text
Required environment variable USER_SERVICE_URL is not set
```

Feature-specific requirements are checked only when the feature is enabled.
For example, Keycloak client secret validation should be conditional on
`KEYCLOAK_ENABLED=true` where the service requires a confidential client.

## Implementation Order

1. Add tests for the common fail-fast contract in the smallest service surface:
   tools-service settings and rag-service auth/config access.
2. Add `apps/tools-service/src/core/settings.py` and migrate tools-service core
   env reads to it.
3. Update `apps/rag-service/langconnect/config.py` to expose a typed
   `Settings` object and migrate non-config direct env reads to config.
4. Migrate agent-service direct env reads to `core.settings` or `core.env`
   accessors, then converge duplicated defaults into `core.settings`.
5. Migrate user-service direct env reads to `src.config` or `src.core.env`
   accessors, then remove secret fallbacks that bypass required env validation.
6. Add `apps/web/src/lib/env.server.ts` and replace server route fallback URLs.
7. Add a lightweight guard script or test that fails on direct env reads outside
   allowed central modules.
8. Update durable docs if the resulting contract differs from
   `docs/development-environment.md`.

## Testing Strategy

Each implementation step must add or update focused tests first.

Python service validation:

- tools-service: `make -C apps/tools-service validate`
- rag-service: `make -C apps/rag-service validate`
- agent-service: `make -C apps/agent-service validate`
- user-service: `make -C apps/user-service validate`

Web validation:

- `npm --prefix apps/web run lint`
- `npm --prefix apps/web run types:check`
- `npm --prefix apps/web test`

Cross-service guard validation:

- `make env-check`
- `make quality-staged` before push-ready handoff

## Acceptance Criteria

- Runtime code outside central env/config modules no longer directly reads
  `os.environ`, `os.getenv`, or service URL fallbacks from `process.env`.
- Required service URLs and secrets fail with clear missing-variable errors.
- Existing tests remain green for every changed service.
- New tests document the central settings contract.
