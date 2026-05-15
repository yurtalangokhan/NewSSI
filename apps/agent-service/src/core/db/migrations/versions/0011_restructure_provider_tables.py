"""Restructure provider tables: remove user_id from providers, add user_provider_configs.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create user_provider_configs table (FK added later)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_provider_configs (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id              TEXT NOT NULL,
            provider_id          UUID NOT NULL,
            api_key_encrypted    TEXT,
            api_key_fingerprint  TEXT,
            api_base             TEXT,
            api_version          TEXT,
            deployment_name      TEXT,
            default_model        TEXT,
            priority             INTEGER NOT NULL DEFAULT 0,
            custom_config        JSONB DEFAULT '{}'::jsonb,
            is_active            BOOLEAN NOT NULL DEFAULT TRUE,
            time_created         TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated         TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_provider_config UNIQUE (user_id, provider_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_provider_configs_user_priority "
        "ON user_provider_configs (user_id, priority)"
    )

    # 2. Add provider_kind column to providers
    op.execute(
        "ALTER TABLE providers ADD COLUMN IF NOT EXISTS provider_kind TEXT NOT NULL DEFAULT 'url'"
    )

    # 3. Migrate existing URL providers → user_provider_configs
    op.execute("""
        INSERT INTO user_provider_configs (
            id, user_id, provider_id, api_key_encrypted, priority,
            is_active, time_created, time_updated
        )
        SELECT
            gen_random_uuid(),
            user_id,
            id AS provider_id,
            api_key_encrypted,
            (ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY time_created) - 1) AS priority,
            is_active,
            time_created,
            time_updated
        FROM providers
    """)

    # 4a. Insert api_key providers into providers table
    op.execute("""
        INSERT INTO providers (
            id, name, provider_type, provider_kind,
            is_active, is_builtin, config, time_created, time_updated
        )
        SELECT
            id,
            name,
            provider_type,
            'api_key',
            is_active,
            FALSE,
            COALESCE(custom_config, '{}'::jsonb),
            time_created,
            time_updated
        FROM user_providers
    """)

    # 4b. Insert api_key provider configs into user_provider_configs
    op.execute("""
        INSERT INTO user_provider_configs (
            id, user_id, provider_id, api_key_encrypted, api_key_fingerprint,
            api_base, api_version, deployment_name, custom_config,
            priority, is_active, time_created, time_updated
        )
        SELECT
            gen_random_uuid(),
            up.user_id,
            up.id AS provider_id,
            up.api_key_encrypted,
            up.api_key_fingerprint,
            up.api_base,
            up.api_version,
            up.deployment_name,
            COALESCE(up.custom_config, '{}'::jsonb),
            (SELECT COUNT(*) FROM user_provider_configs upc WHERE upc.user_id = up.user_id) AS priority,
            up.is_active,
            up.time_created,
            up.time_updated
        FROM user_providers up
    """)

    # 5. Drop user_id and api_key_encrypted from providers
    op.execute("ALTER TABLE providers DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE providers DROP COLUMN IF EXISTS api_key_encrypted")

    # 6. Remove old unique constraint and old index, add new index
    op.execute(
        "ALTER TABLE providers DROP CONSTRAINT IF EXISTS providers_user_id_provider_type_base_url_key"
    )
    op.execute("DROP INDEX IF EXISTS idx_providers_user_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_providers_kind ON providers (provider_kind)"
    )

    # 7. Add FK constraint
    op.execute("""
        ALTER TABLE user_provider_configs
            ADD CONSTRAINT fk_upc_provider
            FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
    """)

    # 8. Drop old user_providers table
    op.execute("DROP TABLE IF EXISTS user_providers")


def downgrade() -> None:
    # Recreate user_providers
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_providers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             TEXT NOT NULL,
            name                TEXT NOT NULL,
            provider_type       TEXT NOT NULL,
            api_key_encrypted   TEXT,
            api_key_fingerprint TEXT,
            api_base            TEXT,
            api_version         TEXT,
            deployment_name     TEXT,
            custom_config       JSONB DEFAULT '{}'::jsonb,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            time_created        TIMESTAMPTZ NOT NULL DEFAULT now(),
            time_updated        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Restore api_key rows to user_providers from providers + user_provider_configs
    op.execute("""
        INSERT INTO user_providers (
            id, user_id, name, provider_type, api_key_encrypted,
            api_key_fingerprint, api_base, api_version, deployment_name,
            custom_config, is_active, time_created, time_updated
        )
        SELECT
            p.id,
            upc.user_id,
            p.name,
            p.provider_type,
            upc.api_key_encrypted,
            upc.api_key_fingerprint,
            upc.api_base,
            upc.api_version,
            upc.deployment_name,
            COALESCE(upc.custom_config, '{}'::jsonb),
            upc.is_active,
            upc.time_created,
            upc.time_updated
        FROM providers p
        JOIN user_provider_configs upc ON upc.provider_id = p.id
        WHERE p.provider_kind = 'api_key'
    """)

    # Restore user_id and api_key_encrypted on providers
    op.execute("ALTER TABLE providers ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE providers ADD COLUMN IF NOT EXISTS api_key_encrypted TEXT")

    # Restore user_id values from user_provider_configs (url providers)
    op.execute("""
        UPDATE providers p
        SET user_id = upc.user_id,
            api_key_encrypted = upc.api_key_encrypted
        FROM user_provider_configs upc
        WHERE upc.provider_id = p.id AND p.provider_kind = 'url'
    """)

    # Drop api_key provider rows from providers
    op.execute("DELETE FROM providers WHERE provider_kind = 'api_key'")

    # Remove provider_kind column
    op.execute("ALTER TABLE providers DROP COLUMN IF EXISTS provider_kind")

    # Restore old constraint and index
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_providers_user_id ON providers (user_id)"
    )

    # Drop new tables/indexes
    op.execute("DROP INDEX IF EXISTS idx_providers_kind")
    op.execute("DROP TABLE IF EXISTS user_provider_configs")
