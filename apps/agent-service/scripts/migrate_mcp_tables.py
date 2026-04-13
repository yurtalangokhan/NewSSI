#!/usr/bin/env python3
"""Migration script to create MCP tables."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../src")

from core.db.engine import get_session_factory


async def run_migration():
    factory = get_session_factory()
    async with factory() as session:
        print("Creating mcp_provider table...")
        await session.execute("""
            CREATE TABLE IF NOT EXISTS mcp_provider (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL UNIQUE,
                type VARCHAR(50) NOT NULL DEFAULT 'external',
                url VARCHAR(500),
                transport VARCHAR(50) NOT NULL DEFAULT 'streamable_http',
                config JSONB DEFAULT '{}',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
                description TEXT DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        print("Creating mcp_tool table...")
        await session.execute("""
            CREATE TABLE IF NOT EXISTS mcp_tool (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                provider_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT DEFAULT '',
                input_schema JSONB DEFAULT '{}',
                output_schema JSONB DEFAULT '{}',
                metadata JSONB DEFAULT '{}',
                category VARCHAR(100),
                tags JSONB DEFAULT '[]',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                last_synced TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        print("Creating agent_tools table...")
        await session.execute("""
            CREATE TABLE IF NOT EXISTS agent_tools (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agent_id INTEGER NOT NULL,
                tool_id UUID NOT NULL,
                config JSONB DEFAULT '{}',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                order_index INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        await session.commit()
        print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(run_migration())
