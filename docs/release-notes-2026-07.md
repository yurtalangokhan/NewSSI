# Agentic AI Platform release notes draft

This draft summarizes the product, platform, and operational progress on the
`dev` branch between May 1, 2026, and July 30, 2026. It is based on the local
Git history because `git fetch origin dev` failed with a GitLab authentication
error.

## Summary

Over the last three months, the platform moved from a prototype-heavy monorepo
toward a release-ready product with clearer service boundaries, stronger
authentication, dynamic authorization, and more complete operational tooling.

The main gains in this period are:

- Kong API Gateway and `/api/v1` service routing were added.
- Authentication ownership was centralized in `user-service`.
- Keycloak, OIDC, LDAP, JWT validation, and external login flows were
  strengthened.
- Dynamic RBAC, a permission catalog, role and permission CRUD, and
  cross-service permission enforcement were added.
- Project management, project files, and chat context resolution were added.
- Long-term memory, memory recall events, and agent/persona integrations were
  improved.
- LLM provider management, vLLM/Ollama provider flows, and vision/file usage
  were expanded.
- RAG gained web crawler ingestion, text insertion, graph build lock,
  pause/resume behavior, and collection mutation safety.
- Ollama model management, GPU operations documentation, and Docker Compose
  tests were added.
- Legacy Supabase monorepo content and unused large structures were removed.
- Development environment setup, Makefile standardization, agent workflow
  documentation, and quality gates were improved.

## Commit summary

The raw non-merge commit distribution for the period is:

- Feature: 75 commits
- Bug fix: 37 commits
- Chore: 10 commits
- Refactor, docs, cleanup, hotfix, and non-standard messages: additional
  maintenance work

Some commits include revert/reapply history or repeated work from branch merges.
For that reason, this release note groups work by product and operational
impact, not only by commit count.

## New features

### Platform and API gateway

Kong API Gateway was introduced as the main external entry point, with Keycloak
integration and OIDC routing support. Service routing now includes `/api/v1`
paths, and web proxy routes were moved onto service-scoped gateway paths.

JWT handling, internal route behavior, service URL configuration, and gateway
documentation were also improved.

### Authentication and user management

`user-service` was added as a dedicated service with Docker setup, an entrypoint
script, and database initialization. Authentication responsibilities were moved
out of `agent-service` and centralized in `user-service`.

Keycloak token refresh, OIDC callback handling, external login redirect URI
support, and cookie handling were improved. LDAP authentication support was
added, and RAG and Tools services now validate Keycloak JWTs.

User registration now requires and validates first name and last name. Change
password, settings authentication, user memory, and pinned assistants flows were
also improved in `user-service`.

### RBAC and permissions

Dynamic role and permission models were added, including a permission catalog,
role CRUD, permission CRUD, and a `require_permission` dependency.

`agent-service` and `rag-service` now perform real permission checks through
`user-service`. The frontend gained permission-based routing, dynamic role
filters, and a role management UI.

Audit logging was added for role CRUD and permission-denied events. Agent access
groups were also introduced to support user-agent group assignment and
visibility gating.

### Agents and memory

Agent composition was added with sub-agent IDs, async graph building, and
composition validation. The persona-agent link model was refactored with a
schema migration and session invalidation support.

Long-term memory capabilities were expanded with memory recall events and event
emitters for configurable agents. Chat timeline behavior was improved with step
turn rules and packet categorization.

Thinking process visibility and tool call displays were also improved.

### Projects and chat context

Project management was added, including project file management and chat service
context resolution. Project files can now be selected and included in chat
context.

App shell routing and authentication redirect behavior were hardened.

### RAG, crawler, and graph build

The Onyx web crawler was added to the web search page. Scraped URL results can
now be converted into RAG collection documents.

Multiple URL parsing, crawler result editing, and Trafilatura-based scraping
support were added. Text-based collection data insertion was also introduced.

Graph RAG build behavior was made safer with collection mutation locking,
pause/resume controls, and UI updates that reflect mutation status.

### LLM providers and model management

The LLM provider page was added with user and common provider management.
Provider update/delete modals, provider components, backend routes, and provider
configuration were improved.

Provider services gained better error handling. vLLM API key usage, cloud
provider naming, and provider endpoint authentication issues were fixed.

Built-in Ollama management and Ollama model management were added, along with
GPU operations documentation and Docker Compose tests.

### Frontend, i18n, and admin screens

i18next integration and broad translation coverage were added. Missing
localizations were restored, and language switching behavior was fixed.

Admin pages gained `AdminOverviewPanel`. App branding was moved away from
hardcoded `Onyx` strings and into configurable naming.

Logo handling was refactored to use SVG assets. Chat foreground/icon styling,
drag-and-drop animation, scrolling behavior, and UI/localization issues were
also improved.

## Bug fixes

The main fixes in this period were:

- Login redirect, logout OIDC cookie cleanup, and Keycloak redirect/logout flows
  were fixed.
- Web auth redirects and app shell routing were hardened.
- `/api/permissions` 404 issues were fixed through Kong config, trailing slash
  proxy, and route corrections.
- `require_permission` import issues in `agent-service` and `rag-service` were
  fixed.
- Missing `user-service` `__init__.py` imports were restored.
- RAG/Tools auth tiers and Kong config issues were fixed.
- Docker/Kong `host.docker.internal`, internal route JWT, and Keycloak hostname
  configuration issues were fixed.
- Frontend and backend build blockers were fixed.
- vLLM thinking process output and Airbyte connector chunk visibility were
  fixed.
- `rawPackets` handling was made safe for optional values.
- A null reference risk in pinned assistants preferences was fixed.
- Graph explorer dark mode, collection null checks, and graph build UI issues
  were fixed.
- Hardcoded default admin usage was removed from provider endpoints. Provider
  endpoints now use the browser cookie token.

## Chores, refactors, and maintenance

The main maintenance work in this period was:

- Makefiles were standardized across services.
- Web package metadata was refreshed.
- Staged quality validation flow was aligned.
- Import ordering and miscellaneous cleanup were completed.
- Runtime environment configuration was centralized.
- Development environment setup, environment management scripts, and
  documentation were improved.
- Agent skills, spec-driven agent workflow documentation, and the no-push rule
  were added.
- RAG documentation was updated from PGVector terminology toward Milvus.
- Legacy Supabase monorepo content, unused providers directory content, and root
  Docker Compose leftovers were removed.
- Orphaned Keycloak/Liquibase tables and dead tables were removed from
  `agent-service`.

## Release risks and checks

Before cutting a release, validate the areas most affected by this period of
work:

- Gateway and authentication changes must be smoke tested across login, logout,
  OIDC callback, external login redirect, and cookie scenarios.
- RBAC migration must be tested across role/permission CRUD, permission-denied
  paths, and cross-service permission checks.
- `/api/v1` gateway routing and web proxy paths must be tested end to end.
- Project file context and chat context resolution need regression coverage.
- RAG crawler, graph build pause/resume, and collection mutation lock flows must
  be tested.
- Ollama management and GPU/Docker Compose behavior must be validated in the
  target environment.
- Legacy Supabase cleanup means Docker, environment, and import path checks must
  be included in the release gate.

## Suggested release validation

Run the full local validation gates before release:

```sh
make validate
make docker-verify
npm --prefix apps/web run lint
npm --prefix apps/web run types:check
npm --prefix apps/web test
```

Also run these manual smoke tests:

- Auth: login, logout, OIDC callback, and external login redirect.
- RBAC: admin role CRUD, permission CRUD, forbidden route, and allowed route.
- Chat: normal chat, project-linked chat, and project file context.
- RAG: crawler ingestion, graph build start, graph build pause, and graph build
  resume.
- Ollama: model list, pull, remove, and GPU Compose validation.
