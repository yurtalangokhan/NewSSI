"""Drop 89 orphaned Keycloak + Liquibase + unused tables from agent_service DB.

These tables are leftovers from a time when a Keycloak instance was pointed
at the agent_service database. The current architecture uses:

  - External SSO (https://test-sso.turksat.com.tr/auth) for agent-service auth
  - Keycloak in its own 'keycloak' database on the same Postgres server
  - No service reads/writes these tables — all Keycloak interactions go
    through the REST API (JWKS, admin API, OIDC endpoints)

Tables dropped:
  - 85 Keycloak internal tables (realm, client, user_entity, keycloak_role, ...)
  -  2 Liquibase migration tracking tables (databasechangelog*)
  -  2 Orphaned application tables (user_file, file_project_association)

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# fmt: off
_TABLES_TO_DROP = [
    # ── Keycloak tables ──────────────────────────────────────────────
    "admin_event_entity",
    "associated_policy",
    "authentication_execution",
    "authentication_flow",
    "authenticator_config",
    "authenticator_config_entry",
    "broker_link",
    "client",
    "client_attributes",
    "client_auth_flow_bindings",
    "client_initial_access",
    "client_node_registrations",
    "client_scope",
    "client_scope_attributes",
    "client_scope_client",
    "client_scope_role_mapping",
    "component",
    "component_config",
    "composite_role",
    "credential",
    "default_client_scope",
    "event_entity",
    "fed_user_attribute",
    "fed_user_consent",
    "fed_user_consent_cl_scope",
    "fed_user_credential",
    "fed_user_group_membership",
    "fed_user_required_action",
    "fed_user_role_mapping",
    "federated_identity",
    "federated_user",
    "group_attribute",
    "group_role_mapping",
    "identity_provider",
    "identity_provider_config",
    "identity_provider_mapper",
    "idp_mapper_config",
    "jgroups_ping",
    "keycloak_group",
    "keycloak_role",
    "migration_model",
    "offline_client_session",
    "offline_user_session",
    "org",
    "org_domain",
    "policy_config",
    "protocol_mapper",
    "protocol_mapper_config",
    "realm",
    "realm_attribute",
    "realm_default_groups",
    "realm_enabled_event_types",
    "realm_events_listeners",
    "realm_localizations",
    "realm_required_credential",
    "realm_smtp_config",
    "realm_supported_locales",
    "redirect_uris",
    "required_action_config",
    "required_action_provider",
    "resource_attribute",
    "resource_policy",
    "resource_scope",
    "resource_server",
    "resource_server_perm_ticket",
    "resource_server_policy",
    "resource_server_resource",
    "resource_server_scope",
    "resource_uris",
    "revoked_token",
    "role_attribute",
    "scope_mapping",
    "scope_policy",
    "user_attribute",
    "user_consent",
    "user_consent_client_scope",
    "user_entity",
    "user_federation_config",
    "user_federation_mapper",
    "user_federation_mapper_config",
    "user_federation_provider",
    "user_group_membership",
    "user_required_action",
    "user_role_mapping",
    "web_origins",
    # ── Liquibase migration tracking ─────────────────────────────────
    "databasechangelog",
    "databasechangeloglock",
    # ── Orphaned application tables (0 rows, no model) ───────────────
    "file_project_association",
    "user_file",
]
# fmt: on


def upgrade() -> None:
    for table in _TABLES_TO_DROP:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    # Nothing to recreate — these tables were never managed by agent-service
    # migrations and Keycloak recreates them automatically if needed.
    pass
