# ResponseModel migration checklist

Track the staged migration of application HTTP routes to the approved response
contract. A checked route means its implementation and known consumers are
migrated; runtime verification is tracked separately below.

## Contract

Each service owns a Pydantic `ResponseModel[T]` with `statusCode`, `message`,
`data`, and nullable `error` (`code` and `message`). Routes call controllers,
controllers call services, and shared typed exceptions propagate to the route.
Exceptions use locale keys from error_contract. Routes set the actual HTTP
status and render the message for the request language. Browser domain APIs and
internal clients check the response status and unwrap `data`.

## Order and completion criteria

User-service, RAG, and agent-service application JSON groups are implemented.
Raw files and sockets retain their protocols. Agent SSE producers use a
service-local StreamEventModel while retaining their existing wire payloads.
Health, readiness, graph-health, and metrics retain their existing operational
protocols in every service. MCP transport has its own protocol decisions.
For every group, track route wrapping, controller/service boundaries, typed
errors, frontend consumers, internal consumers, and verification together.

- [x] Preserve the approved agent catalog/detail/composition pilot.
- [x] Add local models to RAG, user-service, and tools-service.
- [x] RAG datasource routes, domain controller/service, and DTOs.
- [x] RAG datasource browser and agent-service consumers.
- [x] Collection-not-found exception and central en/tr locale key.
- [ ] Verify RAG datasource runtime responses, locale selection, and clients.
- [x] RAG memory and retrieval routes, controllers/services, and internal clients.
- [x] Memory/retrieval exception classes and central en/tr keys.
- [ ] Verify memory/retrieval runtime responses and adapt existing tests.
- [x] RAG collections, documents, and graph groups.
- [x] User-service settings/shortcuts: 10 routes, browser and internal clients.
- [ ] Verify user settings/shortcuts runtime and adapt existing tests.
- [x] Remaining user-service JSON groups, including internal/auth routes.
- [x] User-service global auth/validation/unexpected/idempotency responses.
- [x] User-service CSV transport retained; all 143 registrations accounted for.
- [ ] Verify full user-service runtime, auth cookies, locale, and clients.
- [x] Remaining RAG JSON groups and named frontend/internal consumers.
- [x] RAG global auth/validation/unexpected/idempotency responses.
- [ ] Verify full RAG runtime and adapt existing route/client tests.
- [x] Remaining agent-service JSON groups.
- [x] All health/readiness/metrics excluded from application response migration.
- [x] Agent MCP administration JSON routes and consumers; tools MCP protocol retained.
- [x] Service-local auth, validation, and unexpected-error handlers returning
      ResponseModel, including failures raised before route execution.
- [x] Agent SSE model/serialization/localized error events; raw file/socket protocols retained.
- [ ] Update matching existing tests for moved modules and response shapes.
- [x] Source review of frontend and internal consumers.
- [ ] Requested runtime verification.

## Local models

The local models have the same fields; error_contract contains no response
model. Every HTTP service keeps `response_models.py` beside `response_errors.py`
in its cross-cutting package, and every router reports failures through
`set_error_response` and `request_locale` from `response_errors`. RAG source moved to `src/` during this batch.

| Service | Model |
| --- | --- |
| RAG | `apps/rag-service/src/shared/response_models.py` |
| User | `apps/user-service/src/core/response_models.py` |
| Tools | `apps/tools-service/src/models/response_models.py` (`response_errors.py` beside it) |
| Agent | `apps/agent-service/src/core/http/response_models.py` |

## Error contract follow-up

Shared exception code rendering uses class metadata without constructing domain
exceptions. Reused codes keep canonical metadata; connector categories and
startup failures have safe EN/TR translations. Core exception imports load HTTP
adapters only when requested. Legacy adapter imports remain supported.

User-service and RAG framework error adapters retain the shared handler's status,
code, localized message, and filtered headers while returning the local response
model. Backend diagnostic messages remain suppressed for framework server errors.
Connector resolution forwards the selected language and preserves typed failures
at the native MCP boundary. Microsoft connector configuration, caller input, and
transport failures retain their categories and original causes.

Rejected project uploads render central locale keys instead of raw exception
text. Frontend upload warnings and gateway-generated 413/503/504 responses use
the selected language. Chat history unwraps `data`; tool-status failures retain
the structured error code and localized message. The browser decoder rejects
HTTP/body status mismatches, including error responses. Cancellation and native
proxy forwarding retain their behavior.

Focused package, framework adapter, connector, and upload tests cover these
paths. All 93 tests in the 14 affected frontend suites pass. User/RAG adapter
tests run independently of unrelated service fixtures; this is narrower than a
full application startup check. Full-service runtime verification remains tracked by the unchecked items
above; focused adapter tests do not verify every migrated route.

## Route inventory

The inventory includes all decorated application routes in the service router
folders and service entrypoints, including internal routers. Paths below are
router-local; the enclosing API version or gateway prefix still applies.
Generated OpenAPI/docs endpoints and mounted MCP JSON-RPC methods are tracked
as transport surfaces rather than application JSON routes. A transport label
other than `json` means an explicit conversion decision is pending.

### tools-service (2 routes)

The following entries track this service by source file.

#### `apps/tools-service/server.py`

Track the endpoints owned by this module.

- [x] `GET /health` (`health_check`) — excluded; native operational response
- [x] `GET /health/ready` (`readiness_check`) — excluded; native operational response

### rag-service (44 routes)

The following entries track this service by source file.

#### `apps/rag-service/src/collections/router.py`

Track the endpoints owned by this module.

- [x] `POST /collections` (`collections_create`)
- [x] `GET /collections` (`collections_list`)
- [x] `GET /collections/{collection_id}` (`collections_get`)
- [x] `DELETE /collections/{collection_id}` (`collections_delete`) — HTTP 200 with JSON acknowledgement
- [x] `DELETE /collections/{collection_id}/force` (`collections_force_delete`) — HTTP 200 with JSON acknowledgement
- [x] `PATCH /collections/{collection_id}` (`collections_update`)

#### `apps/rag-service/src/datasources/router.py`

Track the endpoints owned by this module.

- [x] `GET /datasources/knowledge-selector` (`knowledge_selector`)
- [x] `POST /datasources/{collection_id}/records` (`ingest_datasource_records`)
- [x] `GET /datasources/{collection_id}/entities` (`list_datasource_entities`)

#### `apps/rag-service/src/documents/router.py`

Track the endpoints owned by this module.

- [x] `POST /collections/{collection_id}/documents` (`documents_create`)
- [x] `POST /collections/{collection_id}/documents/upload-jobs` (`documents_upload_job_start`)
- [x] `GET /collections/{collection_id}/documents/upload-jobs/status` (`documents_upload_job_status`)
- [x] `GET /collections/{collection_id}/documents` (`documents_list`)
- [x] `GET /collections/{collection_id}/documents/{document_id}/chunks` (`documents_list_chunks`)
- [x] `DELETE /collections/{collection_id}/documents/{document_id}` (`documents_delete`)
- [x] `POST /collections/{collection_id}/documents/search` (`documents_search`)

#### `apps/rag-service/src/graph/router.py`

Track the endpoints owned by this module.

- [x] `POST /graph/build` (`build_graph`)
- [x] `GET /graph/build/{collection_id}/status` (`get_build_status`)
- [x] `POST /graph/build/{collection_id}/pause` (`pause_build`)
- [x] `POST /graph/build/{collection_id}/resume` (`resume_build`)
- [x] `POST /graph/build/{collection_id}/stop` (`stop_build`)
- [x] `GET /graph/collections` (`list_graph_collections`)
- [x] `GET /graph/collections/{collection_id}/nodes` (`list_nodes`)
- [x] `GET /graph/collections/{collection_id}/edges` (`list_edges`)
- [x] `GET /graph/collections/{collection_id}/data` (`get_graph_data`)
- [x] `GET /graph/collections/{collection_id}/data/scalable` (`get_scalable_graph_data`)
- [x] `GET /graph/collections/{collection_id}/neighborhood` (`get_neighborhood`)
- [x] `GET /graph/collections/{collection_id}/expand` (`expand_cluster`)
- [x] `GET /graph/collections/{collection_id}/stats` (`get_graph_stats`)
- [x] `GET /graph/collections/{collection_id}/stats/labels` (`get_labels_paginated`)
- [x] `GET /graph/collections/{collection_id}/stats/relationship-types` (`get_relationship_types_paginated`)
- [x] `POST /graph/search` (`search_graph`)
- [x] `GET /graph/collections/{collection_id}/search/entities` (`search_entities`)
- [x] `GET /graph/collections/{collection_id}/search/entity-clusters` (`search_entity_clusters`)
- [x] `POST /graph/cypher` (`execute_cypher`)
- [x] `DELETE /graph/collections/{collection_id}` (`delete_graph`) — HTTP 200 with JSON acknowledgement
- [x] `GET /graph/health` (`graph_health`) — excluded; native operational response

#### `apps/rag-service/src/memory/router.py`

Track the endpoints owned by this module.

- [x] `POST /memory/facts` (`upsert_fact`) — HTTP 200 with JSON acknowledgement
- [x] `DELETE /memory/facts/{fact_id}` (`delete_fact`) — HTTP 200 with JSON acknowledgement
- [x] `DELETE /memory/facts` (`delete_all_facts`) — HTTP 200 with JSON acknowledgement
- [x] `POST /memory/search` (`search_facts`)

#### `apps/rag-service/src/retrieval/router.py`

Track the endpoints owned by this module.

- [x] `POST /retrieval` (`retrieve_knowledge`)

#### `apps/rag-service/src/server.py`

Track the endpoints owned by this module.

- [x] `GET f'{API_PREFIX}/health'` (`api_health_check`) — excluded; native operational response
- [x] `GET f'{API_PREFIX}/health/ready'` (`api_readiness_check`) — excluded; native operational response

## Completed service phases

User-service: all 139 application JSON routes are implemented; three health
registrations and CSV export retain their native protocols. RAG: all 41
application JSON registrations are implemented, including collections (6),
documents (7), graph (20), and the previously
completed datasource/memory/retrieval groups (8). Local global errors and
idempotency use the same envelope. Browser and internal consumers unwrap data.
Readiness remains native with HTTP 503; create/upload preserve 201/202.

Python compilation, changed-file service Ruff, TypeScript syntax, locale-key
and placeholder consistency, and whitespace checks pass. Runtime tests and a
full frontend type check remain pending. No validate wrappers or hooks ran.

### user-service (143 routes)

The following entries track this service by source file.

#### `apps/user-service/src/api/routes/api_keys_route.py`

Track the endpoints owned by this module.

- [x] `POST /users/me/api-keys/` (`create_key`)
- [x] `GET /users/me/api-keys/` (`list_keys`)
- [x] `DELETE /users/me/api-keys/{key_id}` (`delete_key`)

#### `apps/user-service/src/api/routes/audit_route.py`

Track the endpoints owned by this module.

- [x] `POST /internal/audit-logs` (`create_audit_log`)

#### `apps/user-service/src/api/routes/auth_base_route.py`

Track the endpoints owned by this module.

- [x] `GET /auth/type` (`get_auth_type`)
- [x] `POST /auth/login` (`login`)
- [x] `POST /auth/external/login` (`external_login`)
- [x] `POST /auth/logout` (`logout`)
- [x] `POST /auth/refresh` (`refresh`)
- [x] `GET /auth/oidc/authorize` (`oidc_authorize`)
- [x] `GET /auth/oidc/callback` (`oidc_callback`)
- [x] `GET /auth/me` (`get_me`)
- [x] `POST /auth/sync-users` (`sync_users`)

#### `apps/user-service/src/api/routes/auth_own_route.py`

Track the endpoints owned by this module.

- [x] `POST /auth/register` (`register`)

#### `apps/user-service/src/api/routes/coarse_roles_route.py`

Track the endpoints owned by this module.

- [x] `GET /coarse-roles/` (`list_coarse_roles`)
- [x] `POST /coarse-roles/` (`create_coarse_role`)
- [x] `GET /coarse-roles/aggregated/` (`get_aggregated_permissions`)
- [x] `GET /coarse-roles/service-clients/list` (`list_service_clients`)
- [x] `GET /coarse-roles/{role_id}` (`get_coarse_role`)
- [x] `PATCH /coarse-roles/{role_id}` (`update_coarse_role`)
- [x] `DELETE /coarse-roles/{role_id}` (`delete_coarse_role`)
- [x] `GET /coarse-roles/{role_id}/permissions` (`get_coarse_role_permissions`)
- [x] `PUT /coarse-roles/{role_id}/permissions` (`set_coarse_role_permissions`)

#### `apps/user-service/src/api/routes/health.py`

Track the endpoints owned by this module.

- [x] `GET ` (`health_check`) — excluded; native operational response
- [x] `GET /` (`health_check`) — excluded; native operational response
- [x] `GET /ready` (`readiness_check`) — excluded; native operational response

#### `apps/user-service/src/api/routes/organizations_route.py`

Track the endpoints owned by this module.

- [x] `GET /organizations` (`list_organizations`)
- [x] `POST /organizations` (`create_organization`)
- [x] `GET /organizations/scope` (`get_organization_scope`)
- [x] `GET /organizations/tree` (`get_organization_tree`)
- [x] `GET /organizations/stats` (`get_organization_stats`)
- [x] `GET /organizations/search` (`search_organizations`)
- [x] `GET /organizations/members` (`get_all_organization_members`)
- [x] `GET /organizations/{org_id}` (`get_organization`)
- [x] `GET /organizations/{org_id}/management-capability` (`get_management_capability`)
- [x] `PATCH /organizations/{org_id}` (`update_organization`)
- [x] `DELETE /organizations/{org_id}` (`delete_organization`) — no-content
- [x] `POST /organizations/{org_id}/move` (`move_organization`)
- [x] `GET /organizations/{org_id}/children` (`get_organization_children`)
- [x] `GET /organizations/{org_id}/ancestors` (`get_organization_ancestors`)

#### `apps/user-service/src/api/routes/permissions_route.py`

Track the endpoints owned by this module.

- [x] `GET /permissions/` (`list_permissions`)
- [x] `GET /permissions/entities` (`list_entities`)
- [x] `GET /permissions/services` (`list_services`)
- [x] `POST /permissions/sync` (`sync_permissions`)
- [x] `GET /permissions/coverage` (`get_permission_coverage`)
- [x] `GET /permissions/{permission_name}` (`get_permission`)

#### `apps/user-service/src/api/routes/resource_permissions_route.py`

Track the endpoints owned by this module.

- [x] `GET /permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}/workspace` (`get_organization_workspace`)
- [x] `GET /permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` (`get_scoped_direct_permissions`)
- [x] `PUT /permissions/organizations/{org_id}/targets/{target_type}/{target_id}/resources/{resource_type}` (`sync_scoped_direct_permissions`)
- [x] `POST /permissions/check` (`check_permission`)
- [x] `POST /permissions/organizations/{org_id}/resources` (`grant_organization_permission`)
- [x] `GET /permissions/organizations/{org_id}/resources` (`get_organization_permissions`)
- [x] `POST /permissions/users/{target_user_id}/resources` (`grant_user_permission`)
- [x] `GET /permissions/users/{target_user_id}/resources` (`get_user_permissions`)
- [x] `GET /permissions/users/{target_user_id}/accessible-resources` (`get_user_accessible_resources`)
- [x] `GET /permissions/users/me/resources` (`get_my_accessible_resources`)
- [x] `GET /permissions/resources/{resource_type}/{resource_id}` (`get_resource_permissions`)
- [x] `PATCH /permissions/permissions/{permission_id}` (`update_permission`)
- [x] `DELETE /permissions/permissions/{permission_id}` (`revoke_permission`)
- [x] `POST /permissions/resources/{resource_type}/{resource_id}/bulk-grant` (`bulk_grant_permissions`)
- [x] `GET /permissions/audit/resources/{resource_type}/{resource_id}` (`get_resource_audit_logs`)
- [x] `GET /permissions/audit/organizations/{org_id}` (`get_organization_audit_logs`)
- [x] `GET /permissions/audit/users/{target_user_id}` (`get_user_audit_logs`)
- [x] `GET /permissions/audit/recent` (`get_recent_audit_logs`)

#### `apps/user-service/src/api/routes/roles_route.py`

Track the endpoints owned by this module.

- [x] `GET /roles/` (`list_roles`)
- [x] `POST /roles/` (`create_role`)
- [x] `GET /roles/{role_id}` (`get_role`)
- [x] `PATCH /roles/{role_id}` (`update_role`)
- [x] `DELETE /roles/{role_id}` (`delete_role`)
- [x] `GET /roles/{role_id}/permissions` (`get_role_permissions`)
- [x] `PUT /roles/{role_id}/permissions` (`set_role_permissions`)
- [x] `GET /roles/{role_id}/role-ids` (`get_role_bundles`)
- [x] `PUT /roles/{role_id}/role-ids` (`set_role_bundles`)

#### `apps/user-service/src/api/routes/settings_route.py`

Track the endpoints owned by this module.

- [x] `GET /users/me/settings/` (`get_settings`)
- [x] `PATCH /users/me/settings/` (`update_settings`)
- [x] `POST /users/me/settings/prompt-shortcuts` (`create_prompt_shortcut`)
- [x] `PATCH /users/me/settings/prompt-shortcuts/{shortcut_id}` (`update_prompt_shortcut`)
- [x] `DELETE /users/me/settings/prompt-shortcuts/{shortcut_id}` (`delete_prompt_shortcut`)
- [x] `GET /internal/users/{target_id}/settings` (`get_settings_internal`)
- [x] `PATCH /internal/users/{target_id}/settings` (`update_settings_internal`)
- [x] `POST /internal/users/{target_id}/settings/prompt-shortcuts` (`create_prompt_shortcut_internal`)
- [x] `PATCH /internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` (`update_prompt_shortcut_internal`)
- [x] `DELETE /internal/users/{target_id}/settings/prompt-shortcuts/{shortcut_id}` (`delete_prompt_shortcut_internal`)

#### `apps/user-service/src/api/routes/system_settings_route.py`

Track the endpoints owned by this module.

- [x] `GET /system-settings/keycloak` (`get_keycloak_settings`)
- [x] `PATCH /system-settings/keycloak` (`update_keycloak_settings`)
- [x] `PATCH /system-settings/keycloak/realm-session` (`update_realm_session_settings`)
- [x] `POST /system-settings/keycloak/external-idp/sync` (`sync_external_identity_provider`)

#### `apps/user-service/src/api/routes/user_memory_route.py`

Track the endpoints owned by this module.

- [x] `GET /users/me/memories` (`list_memories`)
- [x] `POST /users/me/memories` (`create_memory`)
- [x] `GET /users/me/memories/{memory_id}` (`get_memory`)
- [x] `PATCH /users/me/memories/{memory_id}` (`update_memory`)
- [x] `DELETE /users/me/memories/{memory_id}` (`delete_memory`) — no-content
- [x] `DELETE /users/me/memories` (`delete_all_memories`)
- [x] `GET /internal/users/{target_id}/memories` (`list_memories_internal`)
- [x] `GET /internal/users/{target_id}/memories/recall` (`list_memories_for_recall_internal`)
- [x] `POST /internal/users/{target_id}/memories` (`create_memory_internal`)
- [x] `POST /internal/users/{target_id}/memories/bulk` (`add_facts_internal`)
- [x] `GET /internal/users/{target_id}/memories/{memory_id}` (`get_memory_internal`)
- [x] `PATCH /internal/users/{target_id}/memories/{memory_id}` (`update_memory_internal`)
- [x] `DELETE /internal/users/{target_id}/memories/{memory_id}` (`delete_memory_internal`) — no-content
- [x] `DELETE /internal/users/{target_id}/memories` (`delete_all_memories_internal`)

#### `apps/user-service/src/api/routes/user_organizations_route.py`

Track the endpoints owned by this module.

- [x] `GET /organizations/{org_id}/assignable-users` (`get_assignable_users`)
- [x] `GET /organizations/{org_id}/users` (`get_organization_users`)
- [x] `POST /organizations/{org_id}/users` (`assign_user_to_organization`)
- [x] `POST /organizations/{org_id}/users/bulk` (`bulk_assign_users_to_organization`)
- [x] `PATCH /organizations/{org_id}/users/{target_user_id}` (`update_user_organization`)
- [x] `DELETE /organizations/{org_id}/users/{target_user_id}` (`remove_user_from_organization`)
- [x] `GET /users/{target_user_id}/organizations` (`get_user_organizations`)
- [x] `GET /users/me/organizations` (`get_my_organizations`)
- [x] `POST /users/{target_user_id}/organizations/{org_id}/set-primary` (`set_primary_organization`)
- [x] `GET /users/{target_user_id}/organizations/primary` (`get_primary_organization`)
- [x] `GET /users/{target_user_id}/organizations/managed` (`get_managed_organizations`)

#### `apps/user-service/src/api/routes/user_route.py`

Track the endpoints owned by this module.

- [x] `GET /users/me` (`get_me`)
- [x] `GET /users/me/permissions` (`get_me_permissions`)
- [x] `GET /users/me/roles` (`get_me_roles`)
- [x] `PATCH /users/me` (`update_me`)
- [x] `POST /users/me/password` (`change_me_password`)
- [x] `GET /users/` (`list_users`)
- [x] `POST /users/` (`create_user`)
- [x] `GET /users/invited` (`get_invited_users`)
- [x] `GET /users/role-distribution` (`get_role_distribution`)
- [x] `GET /users/download/csv` (`download_csv`) — stream
- [x] `POST /internal/users/batch` (`get_users_by_ids_internal`)
- [x] `POST /internal/users/upsert-from-keycloak` (`upsert_user_from_keycloak`)
- [x] `POST /users/internal/upsert-from-keycloak` (`upsert_user_from_keycloak`)
- [x] `GET /internal/users/by-keycloak-id/{keycloak_id}` (`get_user_by_keycloak_id`)
- [x] `PATCH /internal/users/{target_id}` (`update_user_internal`)
- [x] `GET /internal/users/{target_id}/permissions` (`get_user_permissions_internal`)
- [x] `GET /internal/users/{target_id}/effective-permissions` (`get_user_effective_permissions_internal`)
- [x] `GET /internal/users/{target_id}/roles` (`get_user_roles_internal`)
- [x] `POST /internal/users/authorize` (`authorize_user_permission_internal`)
- [x] `POST /users/invite` (`invite_users`)
- [x] `POST /users/{target_id}/role` (`replace_user_role`)
- [x] `GET /users/{target_id}/roles` (`list_user_roles`)
- [x] `POST /users/{target_id}/roles` (`assign_user_roles`)
- [x] `DELETE /users/{target_id}/roles/{role_id}` (`remove_user_role`)
- [x] `POST /users/{target_id}/roles/{role_id}/primary` (`set_primary_user_role`)
- [x] `POST /users/{target_id}/reset-password` (`reset_user_password`)
- [x] `PATCH /users/{target_id}/active` (`set_user_active`)
- [x] `POST /users/{target_id}/password` (`set_user_password`)
- [x] `GET /users/{target_id}` (`get_user`)
- [x] `PATCH /users/{target_id}` (`update_user`)
- [x] `DELETE /users/{target_id}` (`delete_user`)

### agent-service (206 routes)

The following entries track this service by source file.

#### `apps/agent-service/src/api/routes/admin_mcp_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/admin/mcp/server/{server_id}` (`get_mcp_server`)

#### `apps/agent-service/src/api/routes/agent_definitions_route.py`

Track the endpoints owned by this module.

- [x] `GET /agent-definitions/schemas/list` (`list_schemas`)
- [x] `GET /agent-definitions/brains/list` (`list_brain_types`)
- [x] `GET /agent-definitions/memory/list` (`list_memory_types`)
- [x] `POST /agent-definitions` (`create_agent_definition`)
- [x] `GET /agent-definitions` (`list_agent_definitions`)
- [x] `POST /agent-definitions/validate-composition` (`validate_composition`)
- [x] `POST /agent-definitions/available-for-composition` (`get_available_for_composition`)
- [x] `POST /agent-definitions/validate-flow` (`validate_flow`)
- [x] `GET /agent-definitions/{definition_id}/composition-info` (`get_composition_info`)
- [x] `PUT /agent-definitions/{definition_id}/sub-agents` (`update_sub_agents`)
- [x] `POST /agent-definitions/{definition_id}/expand` (`expand_agent_definition_route`)
- [x] `GET /agent-definitions/{definition_id}` (`get_agent_definition`)
- [x] `PUT /agent-definitions/{definition_id}` (`update_agent_definition`)
- [x] `DELETE /agent-definitions/{definition_id}` (`delete_agent_definition`)

#### `apps/agent-service/src/api/routes/agent_tools_route.py`

Track the endpoints owned by this module.

- [x] `GET /assistants/{agent_id}/tools` (`get_agent_tools`)
- [x] `POST /assistants/{agent_id}/tools` (`add_tools_to_agent`)
- [x] `POST /assistants/{agent_id}/tools/{tool_id}` (`add_tool_to_agent`)
- [x] `DELETE /assistants/{agent_id}/tools/{tool_id}` (`remove_tool_from_agent`)
- [x] `PUT /assistants/{agent_id}/tools/reorder` (`reorder_agent_tools`)

#### `apps/agent-service/src/api/routes/agents_route.py`

Track the endpoints owned by this module.

- [x] `GET /agents/info` (`info`)
- [x] `GET /agents/catalog` (`agent_catalog`)
- [x] `GET /agents/composition/catalog` (`agent_composition_catalog`)
- [x] `GET /agents/{agent_id}` (`agent_detail`)
- [x] `POST /agents/{agent_id}/invoke` (`invoke`)
- [x] `POST /agents/{agent_id}/stream` (`stream`) — stream
- [x] `POST /agents/feedback` (`feedback`)
- [x] `POST /agents/history` (`history`)

#### `apps/agent-service/src/api/routes/assistant_schemas_route.py`

Track the endpoints owned by this module.

- [x] `GET /assistants/{assistant_id}/schemas` (`get_assistant_schemas`)

#### `apps/agent-service/src/api/routes/assistants_route.py`

Track the endpoints owned by this module.

- [x] `POST /assistants/search` (`search_assistants`)
- [x] `GET /assistants/{assistant_id}` (`get_assistant`)
- [x] `POST /assistants` (`create_assistant`)
- [x] `PATCH /assistants/{assistant_id}` (`update_assistant`)
- [x] `DELETE /assistants/{assistant_id}` (`delete_assistant`)

#### `apps/agent-service/src/api/routes/chat_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/chat/sessions` (`get_chat_sessions`)
- [x] `POST /api/chat/sessions` (`create_chat_session`)
- [x] `GET /api/chat/sessions/{chat_session_id}` (`get_chat_session`)
- [x] `DELETE /api/chat/sessions/{chat_session_id}` (`delete_chat_session`)
- [x] `DELETE /api/chat/delete-all-chat-sessions` (`delete_all_chat_sessions`)
- [x] `PUT /api/chat/rename-chat-session` (`rename_chat_session`)
- [x] `PUT /api/chat/update-chat-session-model` (`update_chat_session_model`)
- [x] `PUT /api/chat/update-chat-session-temperature` (`update_chat_session_temperature`)
- [x] `POST /api/chat/stop-chat-session/{chat_session_id}` (`stop_chat_session`)
- [x] `PUT /api/chat/set-message-as-latest` (`set_message_as_latest`)
- [x] `GET /api/chat/available-context-tokens/{session_id}` (`get_available_context_tokens`)
- [x] `GET /user/projects/session/{session_id}/token-count` (`get_session_token_count`)
- [x] `GET /user/projects/session/{session_id}/files` (`get_session_files`)
- [x] `POST /api/chat/create-chat-message-feedback` (`create_chat_message_feedback`)
- [x] `DELETE /api/chat/remove-chat-message-feedback` (`remove_chat_message_feedback`)
- [x] `POST /api/chat/messages` (`send_chat_message`) — stream

#### `apps/agent-service/src/api/routes/connector_tools_route.py`

Track the endpoints owned by this module.

- [x] `GET /datasources/tool-options` (`connector_options`)
- [x] `POST /internal/connector-tools/resolve` (`resolve_connector`)

#### `apps/agent-service/src/api/routes/datasources_route.py`

Track the endpoints owned by this module.

- [x] `GET /datasources/connectors` (`list_connectors`)
- [x] `GET /datasources/connectors/{connector_name}/spec` (`get_connector_specification`)
- [x] `POST /datasources/connectors/{connector_name}/validate` (`validate_connector_configuration`)
- [x] `POST /datasources/connectors/{connector_name}/streams` (`get_connector_streams`)
- [x] `GET /datasources` (`list_datasources`)
- [x] `POST /datasources` (`create_datasource`)
- [x] `GET /datasources/{id}/details` (`get_datasource_details`)
- [x] `PUT /datasources/{id}` (`update_datasource`)
- [x] `POST /datasources/{id}/sync` (`sync_datasource`)
- [x] `GET /datasources/{id}/status` (`get_sync_status`)
- [x] `GET /datasources/{id}/sync-history` (`get_sync_history`)
- [x] `DELETE /datasources/{id}` (`delete_datasource`)

#### `apps/agent-service/src/api/routes/file_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/chat/file/{file_id}` (`get_chat_file`) — raw-response
- [x] `GET /api/chat/file/{file_id}/text` (`get_chat_file_text`) — raw-response

#### `apps/agent-service/src/api/routes/flow_components_route.py`

Track the endpoints owned by this module.

- [x] `GET /flow-components` (`list_components`)
- [x] `GET /flow-components/options/{source}` (`resolve_component_options`)
- [x] `GET /flow-components/{component_type}` (`get_component`)

#### `apps/agent-service/src/api/routes/flow_playground_route.py`

Track the endpoints owned by this module.

- [x] `POST /agent-definitions/{definition_id}/flow/playground/runs/stream` (`run_flow_playground_stream`) — stream
- [x] `POST /agent-definitions/flow/playground/runs/stream` (`run_flow_playground_inline_stream`) — stream

#### `apps/agent-service/src/api/routes/flow_versions_route.py`

Track the endpoints owned by this module.

- [x] `GET /agent-definitions/{definition_id}/flow/draft` (`get_draft`)
- [x] `GET /agent-definitions/{definition_id}/flow/published` (`get_published`)
- [x] `PUT /agent-definitions/{definition_id}/flow/draft` (`save_draft`)
- [x] `DELETE /agent-definitions/{definition_id}/flow/draft` (`discard_draft`) — no-content
- [x] `GET /agent-definitions/{definition_id}/flow/versions` (`list_versions`)
- [x] `GET /agent-definitions/{definition_id}/flow/versions/{version_no}` (`get_version_detail`)
- [x] `POST /agent-definitions/{definition_id}/flow/publish` (`publish_flow`)
- [x] `POST /agent-definitions/{definition_id}/flow/rollback` (`rollback_flow`)

#### `apps/agent-service/src/api/routes/ingest_route.py`

Track the endpoints owned by this module.

- [x] `POST /batch` (`ingest_batch`)
- [x] `POST /source-preview` (`source_preview`)

#### `apps/agent-service/src/api/routes/mail_configs_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/mail-configs/available` (`list_available_mail_configs`)
- [x] `GET /api/mail-configs/user-credentials` (`get_user_mail_credentials`)
- [x] `PUT /api/mail-configs/user-credentials` (`upsert_user_mail_credentials`)
- [x] `DELETE /api/mail-configs/user-credentials` (`delete_user_mail_credentials`)
- [x] `POST /api/mail-configs/user-credentials/test` (`test_user_mail_credentials`)
- [x] `GET /api/mail-configs` (`list_mail_configs`)
- [x] `POST /api/mail-configs` (`create_mail_config`)
- [x] `GET /api/mail-configs/{config_id}` (`get_mail_config`)
- [x] `PATCH /api/mail-configs/{config_id}` (`update_mail_config`)
- [x] `DELETE /api/mail-configs/{config_id}` (`delete_mail_config`)
- [x] `POST /api/mail-configs/{config_id}/test` (`test_mail_config`)
- [x] `POST /api/mail-configs/{config_id}/send` (`send_mail_with_config`)

#### `apps/agent-service/src/api/routes/mcp_oauth_callback_route.py`

Track the endpoints owned by this module.

- [x] `POST /api/mcp/oauth/callback` (`mcp_oauth_callback`)

#### `apps/agent-service/src/api/routes/mcp_providers_route.py`

Track the endpoints owned by this module.

- [x] `GET /mcp-providers` (`list_providers`)
- [x] `GET /mcp-providers/{provider_id}` (`get_provider`)
- [x] `POST /mcp-providers` (`create_provider`)
- [x] `POST /mcp-providers/{provider_id}/sync` (`sync_provider_tools`)
- [x] `PATCH /mcp-providers/{provider_id}` (`update_provider`)
- [x] `DELETE /mcp-providers/{provider_id}` (`delete_provider`)

#### `apps/agent-service/src/api/routes/mcp_server_admin_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/admin/mcp/servers` (`list_mcp_servers`)
- [x] `GET /api/admin/mcp/servers/{server_id}` (`get_mcp_server`)
- [x] `POST /api/admin/mcp/server` (`create_mcp_server`)
- [x] `PATCH /api/admin/mcp/server/{server_id}` (`update_mcp_server`)
- [x] `DELETE /api/admin/mcp/server/{server_id}` (`delete_mcp_server`)
- [x] `PATCH /api/admin/mcp/server/{server_id}/status` (`set_mcp_server_status`)
- [x] `GET /api/admin/mcp/server/{server_id}/tools/snapshots` (`refresh_mcp_server_tools`)
- [x] `POST /api/admin/mcp/server/{server_id}/tools/{tool_name}/execute` (`execute_mcp_server_tool`)
- [x] `POST /api/admin/mcp/servers/create` (`upsert_mcp_server`)
- [x] `POST /api/admin/mcp/oauth/connect` (`mcp_oauth_connect`)
- [x] `PATCH /api/admin/tool/status` (`set_tool_status`)

#### `apps/agent-service/src/api/routes/mcp_tools_route.py`

Track the endpoints owned by this module.

- [x] `GET /mcp-tools` (`list_tools`)
- [x] `GET /mcp-tools/available` (`list_available_tools`)
- [x] `GET /mcp-tools/categories` (`list_categories`)
- [x] `GET /mcp-tools/categories/{category}` (`get_tools_by_category`)
- [x] `GET /mcp-tools/{tool_id}` (`get_tool`)
- [x] `GET /mcp-tools/provider/{provider_id}` (`list_tools_by_provider`)
- [x] `POST /mcp-tools/sync` (`sync_all_tools`)
- [x] `POST /mcp-tools/provider/{provider_id}/sync` (`sync_provider_tools`)
- [x] `DELETE /mcp-tools/{tool_id}` (`delete_tool`)

#### `apps/agent-service/src/api/routes/ollama_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/admin/ollama/status` (`get_builtin_ollama_status`)
- [x] `GET /api/admin/ollama/models` (`list_builtin_ollama_models`)
- [x] `DELETE /api/admin/ollama/models/{model_name:path}` (`delete_builtin_ollama_model`)

#### `apps/agent-service/src/api/routes/persona_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/persona` (`get_personas`)
- [x] `GET /api/persona/options` (`get_persona_options`)
- [x] `GET /api/persona/labels` (`get_persona_labels`)
- [x] `POST /api/persona` (`create_persona`)
- [x] `GET /api/persona/{persona_id}` (`get_persona`)
- [x] `PATCH /api/persona/{persona_id}` (`update_persona`)
- [x] `DELETE /api/persona/{persona_id}` (`delete_persona`)
- [x] `POST /api/admin/persona/upload-image` (`upload_persona_image`)

#### `apps/agent-service/src/api/routes/provider_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/admin/providers` (`list_providers`)
- [x] `GET /api/admin/providers/available-models` (`get_available_models`)
- [x] `POST /api/admin/providers` (`create_provider`)
- [x] `PUT /api/admin/providers/order` (`reorder_providers`)
- [x] `PUT /api/admin/providers/{provider_id}` (`update_provider`)
- [x] `DELETE /api/admin/providers/{provider_id}` (`delete_provider`)
- [x] `PATCH /api/admin/providers/{config_id}/default-model` (`update_default_model`)
- [x] `POST /api/admin/user-providers` (`create_user_provider`)
- [x] `PUT /api/admin/user-providers/{provider_id}` (`update_user_provider`)
- [x] `DELETE /api/admin/user-providers/{provider_id}` (`delete_user_provider`)
- [x] `GET /api/admin/providers/well-known` (`get_well_known_providers`)
- [x] `POST /api/admin/providers/test-connection` (`test_provider_connection`)
- [x] `GET /api/admin/providers/{provider_id}/models` (`get_provider_models`)
- [x] `POST /api/admin/providers/{provider_id}/sync-models` (`sync_provider_models`)
- [x] `POST /api/admin/ollama/pull` (`pull_ollama_model`) — stream
- [x] `GET /api/admin/vllm/models` (`get_vllm_models`)

#### `apps/agent-service/src/api/routes/proxy_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/proxy/mcp/tools` (`get_mcp_tools`)
- [x] `GET /api/proxy/ollama/models` (`get_ollama_models`)
- [x] `GET /api/proxy/rag/collections` (`get_rag_collections`)
- [x] `GET /api/proxy/mcp/tools-builtin` (`get_builtin_mcp_tools`)
- [x] `POST /api/proxy/mcp/execute` (`execute_mcp_tool`)

#### `apps/agent-service/src/api/routes/run_route.py`

Track the endpoints owned by this module.

- [x] `POST /threads/{thread_id}/runs/stream` (`stream_run`) — stream
- [x] `POST /threads/{thread_id}/runs/{run_id}/cancel` (`cancel_run_endpoint`)
- [x] `POST /threads/{thread_id}/history` (`get_thread_history`)

#### `apps/agent-service/src/api/routes/schedule_route.py`

Track the endpoints owned by this module.

- [x] `GET /datasources/schedules` (`list_all_schedules`)
- [x] `POST /datasources/{datasource_id}/schedule` (`create_schedule`)
- [x] `GET /datasources/{datasource_id}/schedule` (`get_schedule`)
- [x] `PUT /datasources/{datasource_id}/schedule` (`update_schedule`)
- [x] `DELETE /datasources/{datasource_id}/schedule` (`delete_schedule`)
- [x] `GET /datasources/{datasource_id}/schedule/status` (`get_schedule_run_status`)

#### `apps/agent-service/src/api/routes/threads_route.py`

Track the endpoints owned by this module.

- [x] `POST /threads/search` (`search_threads`)
- [x] `POST /threads` (`create_thread`)
- [x] `GET /threads/{thread_id}` (`get_thread`)
- [x] `GET /threads/{thread_id}/state` (`get_thread_state`)
- [x] `PATCH /threads/{thread_id}` (`update_thread`)
- [x] `DELETE /threads/{thread_id}` (`delete_thread`)

#### `apps/agent-service/src/api/routes/user_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/user/files/recent` (`get_recent_files`)
- [x] `GET /api/llm/provider` (`get_llm_provider`)
- [x] `GET /api/admin/llm/built-in/options` (`get_llm_built_in_options`)
- [x] `POST /api/admin/llm/test/default` (`test_llm_default`)
- [x] `GET /api/admin/default-assistant` (`get_default_assistant`)
- [x] `GET /api/user/projects` (`get_user_projects`)
- [x] `POST /api/user/projects/create` (`create_user_project`)
- [x] `POST /api/user/projects/file/upload` (`upload_project_files`)
- [x] `GET /api/user/projects/files/{project_id}` (`get_files_in_project`)
- [x] `POST /api/user/projects/{project_id}/files/{file_id}` (`link_file_to_project`)
- [x] `DELETE /api/user/projects/{project_id}/files/{file_id}` (`unlink_file_from_project`)
- [x] `GET /api/user/projects/file/{file_id}` (`get_user_file`)
- [x] `DELETE /api/user/projects/file/{file_id}` (`delete_user_file`)
- [x] `POST /api/user/projects/file/statuses` (`get_user_file_statuses`)
- [x] `GET /api/user/projects/{project_id}` (`get_user_project`)
- [x] `PATCH /api/user/projects/{project_id}` (`rename_user_project`)
- [x] `DELETE /api/user/projects/{project_id}` (`delete_user_project`)
- [x] `GET /api/user/projects/{project_id}/details` (`get_user_project_details`)
- [x] `GET /api/user/projects/{project_id}/instructions` (`get_user_project_instructions`)
- [x] `POST /api/user/projects/{project_id}/instructions` (`upsert_user_project_instructions`)
- [x] `GET /api/user/projects/{project_id}/token-count` (`get_project_token_count`)
- [x] `POST /api/user/projects/{project_id}/move_chat_session` (`move_chat_session_to_project`)
- [x] `POST /api/user/projects/remove_chat_session` (`remove_chat_session_from_project`)
- [x] `GET /admin/llm/provider` (`get_admin_llm_provider`)
- [x] `POST /api/admin/llm/test` (`test_llm`)
- [x] `POST /api/admin/llm/default` (`set_default_llm`)
- [x] `GET /api/admin/llm/ollama/available-models` (`get_ollama_models`)
- [x] `PUT /api/admin/llm/provider` (`save_llm_provider`)
- [x] `POST /api/admin/llm/provider` (`create_llm_provider`)
- [x] `GET /llm/persona/{persona_id}/providers` (`get_persona_providers`)

#### `apps/agent-service/src/api/routes/web_search_route.py`

Track the endpoints owned by this module.

- [x] `GET /api/admin/web-search/search-providers` (`list_search_providers`)
- [x] `GET /api/admin/web-search/content-providers` (`list_content_providers`)
- [x] `POST /api/admin/web-search/content-providers/test` (`test_content_provider`)
- [x] `POST /api/admin/web-search/content-providers/crawl` (`crawl_url`)
- [x] `POST /api/admin/web-search/content-providers/reset-default` (`reset_default_content_provider`)
- [x] `POST /api/admin/web-search/content-providers/{provider_id}/activate` (`activate_content_provider`)
- [x] `POST /api/admin/web-search/content-providers/{provider_id}/deactivate` (`deactivate_content_provider`)

## First batch checks and remaining work

Python syntax (15 files), locale JSON (2 files), TypeScript/TSX syntax
(5 files), and diff whitespace checks pass for this implementation batch.
These checks do not verify runtime behavior or TypeScript types. Runtime tests
and hooks have not been run for this batch.

Update RAG tests to target `src.datasources.service` for business dependencies,
pass FastAPI Response when directly calling migrated routes, and read payloads
under `data`. Existing API tests still expect the prior raw JSON shape.

### Memory and retrieval batch

Five more RAG routes are implemented with controllers and ResponseModel. Memory
writes now return 200 acknowledgements. Agent-service memory recall, user-service
memory writes, and tools-service retrieval clients read the new contract.

New shared classes: DelegatedIdentityRequiredError, TrustedIdentityRequiredError,
GraphSearchPermissionError, CollectionAccessDeniedError, RequiredFieldError,
MemoryUpsertError, and MemoryDeleteError. Reuse ForbiddenTrustedFieldError for
reserved argument rejection (400) and ConfigurationError/DependencyResponseError
for client failures. All new classes have central en/tr locale keys. Memory
repository writes preserve typed errors and translate remaining driver failures;
recall keeps its explicit empty-result recovery behavior.

Python syntax (23 files), the seven new classes' locale keys in both languages,
and diff whitespace checks pass. Runtime tests and hooks were not run. Existing
memory/retrieval tests need controller/service patch targets, wrapped payloads,
and 200 acknowledgements. These internal endpoints have no direct browser
consumer; user-facing memory CRUD remains a separate checklist group.

Next, migrate user-service settings and prompt shortcuts with browser and agent
consumers. Resume the remaining RAG domains after user-service groups. Finish
each consumer chain before checking off its routes.

## User-service completion

All 143 decorated route registrations are accounted for: 139 application JSON
responses use the local model; three health registrations and CSV export retain
their native protocols. Existing 201
responses keep 201; previous 204 memory/organization acknowledgements now use
200 with null data. The health readiness HTTP status remains 503 on failure.
Global dependency, validation, unknown-route, unexpected, and idempotency
errors also use the model. Shared keyed exceptions and EN/TR catalog entries
cover the migrated error paths.

The web session, directory, access, organization, resource, settings, API key,
and memory consumers unwrap at named domain boundaries. Agent, RAG, and tools
clients validate and unwrap their user-service responses. Source review has no
open findings. Python compilation, changed-file Ruff, TypeScript syntax, locale
key/placeholder checks, and whitespace checks are tracked separately from
runtime tests; runtime verification and existing fixture updates remain pending.


#### `apps/agent-service/src/app.py`

Track the entrypoint health JSON operations alongside the router inventory.

- [x] `GET /api/v1/health` (`api_health_check`) — excluded; native operational response
- [x] `GET /api/v1/health/ready` (`api_readiness_check`) — excluded; native operational response

## Agent completion

Agent inventory contains 206 registrations: 196 application JSON routes,
six SSE routes, two file routes, and two native health routes. All 196 JSON
routes use ResponseModel with their original DTO nested in data. Controllers
return domain payloads, services raise typed keyed exceptions, and routes render
localized errors with matching HTTP/body status. Known browser domain APIs,
server consumers, AgentClient, connector resolution, and connector batch ingestion
read data at the boundary. Native external connector protocols retain raw JSON.

All six SSE routes share StreamEventModel serialization through their producers.
Existing payload fields, data-only frames, heartbeat comments, and [DONE] remain.
Stream errors carry error.code/error.message and the existing content field;
errors before streaming starts use the JSON HTTP error handler. HTTP headers
already sent cannot be changed by a later event. Health/metrics and file bytes
retain native protocols. Static checks and source review passed; runtime and
existing-test adaptation remain pending because tests were not requested.
