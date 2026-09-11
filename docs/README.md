# Documentation map

This directory contains repository-wide documentation only. Service-specific
runtime, API, testing, and runbook notes live with the service under
`apps/<service>/docs/`.

Use this map to choose the smallest useful document set for a task.

## Global documents

Read global documents when the work changes shared contracts, cross-service
flows, development rules, deployment, or infrastructure.

| Document | Use it for |
|---|---|
| [Architecture overview](architecture-overview.md) | System context, container boundaries, and service ownership |
| [Service interactions](service-interactions.md) | Cross-service request flows, auth chains, and dependency maps |
| [Coding standards](coding-standards.md) | Repo-wide coding conventions and quality gate rules |
| [OOP and SOLID architecture](oop-solid-architecture.md) | Layering, dependency direction, and architecture gate rules |
| [Developer guide](developer-guide.md) | Repo layout, common commands, validation, and known quirks |
| [Development environment](development-environment.md) | Local setup and startup flow |
| [Environment variables](env-variables.md) | Shared environment variable inventory |
| [Deployment](deployment.md) | Compose, images, startup order, and health checks |
| [Error handling](error-handling.md) | Shared error envelope and exception contract |
| [Idempotency](idempotency.md) | Shared idempotency middleware, service policies, frontend key handling, and coverage assessment |
| [Observability](observability.md) | Startup logging, dependency policy, retry, and readiness contract |
| [Auth login/logout flow](auth-login-logout-flow.md) | Browser auth, cookie, and token lifecycle |
| [Code review skills](code-review-skills.md) | Review workflow recommendations |
| [Deferred architecture work](architecture/deferred-work.md) | Accepted follow-up cleanup backlog |

## Service documents

Read service-local documents when a task touches one service. Start with
`overview.md`, then add only the documents required by the change.

| Service | Documents |
|---|---|
| Agent service | [Overview](../apps/agent-service/docs/overview.md), [architecture](../apps/agent-service/docs/architecture.md), [API](../apps/agent-service/docs/api.md), [testing](../apps/agent-service/docs/testing.md), [runbook](../apps/agent-service/docs/runbook.md) |
| RAG service | [Overview](../apps/rag-service/docs/overview.md), [architecture](../apps/rag-service/docs/architecture.md), [API](../apps/rag-service/docs/api.md), [testing](../apps/rag-service/docs/testing.md), [runbook](../apps/rag-service/docs/runbook.md) |
| User service | [Overview](../apps/user-service/docs/overview.md), [architecture](../apps/user-service/docs/architecture.md), [API](../apps/user-service/docs/api.md), [testing](../apps/user-service/docs/testing.md), [runbook](../apps/user-service/docs/runbook.md) |
| Tools service | [Overview](../apps/tools-service/docs/overview.md), [architecture](../apps/tools-service/docs/architecture.md), [API](../apps/tools-service/docs/api.md), [testing](../apps/tools-service/docs/testing.md), [runbook](../apps/tools-service/docs/runbook.md) |
| Web | [Overview](../apps/web/docs/overview.md), [architecture](../apps/web/docs/architecture.md), [testing](../apps/web/docs/testing.md), [runbook](../apps/web/docs/runbook.md) |

## Generated API artifacts

Prefer the service `api.md` file for human-readable endpoint contracts. Read
generated OpenAPI JSON only when you need schema-level detail or you are
regenerating API documentation.

The repo doesn't yet provide one shared command that exports OpenAPI for every
FastAPI service. Track that improvement in
[deferred architecture work](architecture/deferred-work.md).
