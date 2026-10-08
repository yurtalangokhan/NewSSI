# Web overview

The web app is a Next.js 16 frontend using the Atlas component system and the
`@atlas/opal` workspace. It calls backend services through configured API
rewrites and gateway-facing service paths.

## Source map

| Area | Location |
|---|---|
| App Router pages | `src/app/` |
| Shared components | `src/components/` |
| Atlas refresh components | `src/refresh-components/` |
| Icons | `src/icons/` |
| Hooks | `src/hooks/` |
| Utilities | `src/lib/` |
| Shared workspace library | `lib/opal/` |
| Tests | `tests/`, co-located source tests |

## Documentation

- [Architecture](architecture.md) describes frontend boundaries and API access.
- [Testing](testing.md) describes validation commands.
- [Runbook](runbook.md) covers local startup and runtime checks.
