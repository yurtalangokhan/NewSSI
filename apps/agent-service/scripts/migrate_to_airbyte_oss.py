#!/usr/bin/env python3
"""
Migration script: PyAirbyte → Airbyte OSS Platform.

This script migrates existing datasources from the old sync_schedules table
to the new datasource_airbyte_mapping table.  It also creates Airbyte sources,
connections, and destinations for any datasource that has a stored
connector config.

Usage:
    python scripts/migrate_to_airbyte_oss.py

Requirements:
    - Airbyte OSS platform must be running (docker compose up)
    - PostgreSQL must be accessible
    - Environment variables: DATABASE_URI, AIRBYTE_API_URL
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Ensure the source directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import psycopg
from psycopg.rows import dict_row

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("migrate")

DATABASE_URI = os.environ.get(
    "DATABASE_URI",
    os.environ.get("POSTGRES_URI", "postgresql://postgres:postgres@localhost:5432/postgres"),
)
AIRBYTE_API_URL = os.environ.get("AIRBYTE_API_URL", "http://localhost:8001/api/v1")


async def main() -> None:
    logger.info("Starting migration: PyAirbyte → Airbyte OSS")
    logger.info("Database: %s", DATABASE_URI.split("@")[-1])
    logger.info("Airbyte API: %s", AIRBYTE_API_URL)

    # ------------------------------------------------------------------ #
    # 1.  Ensure the new mapping table exists
    # ------------------------------------------------------------------ #
    logger.info("Step 1: Creating datasource_airbyte_mapping table if needed...")
    async with await psycopg.AsyncConnection.connect(DATABASE_URI) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS datasource_airbyte_mapping (
                    datasource_id   UUID PRIMARY KEY,
                    airbyte_source_id       VARCHAR NOT NULL,
                    airbyte_connection_id    VARCHAR NOT NULL,
                    airbyte_destination_id   VARCHAR NOT NULL,
                    update_graph_rag         BOOLEAN DEFAULT false,
                    last_processed_job_id    BIGINT DEFAULT 0,
                    created_at      TIMESTAMP DEFAULT NOW(),
                    updated_at      TIMESTAMP DEFAULT NOW()
                )
            """)
        await conn.commit()
    logger.info("  ✅ Table ready")

    # ------------------------------------------------------------------ #
    # 2.  Read existing schedules from old table (if exists)
    # ------------------------------------------------------------------ #
    old_schedules: dict[str, dict] = {}
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URI) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM sync_schedules")
                rows = await cur.fetchall()
                for row in rows:
                    old_schedules[str(row["datasource_id"])] = row
        logger.info("Step 2: Found %d existing schedules in sync_schedules", len(old_schedules))
    except Exception:
        logger.info("Step 2: No sync_schedules table found (clean install)")

    # ------------------------------------------------------------------ #
    # 3.  Read all datasources from langchain_pg_collection
    # ------------------------------------------------------------------ #
    datasources: list[dict] = []
    async with await psycopg.AsyncConnection.connect(DATABASE_URI) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT uuid, name, cmetadata FROM langchain_pg_collection")
            rows = await cur.fetchall()
            for row in rows:
                meta = row.get("cmetadata") or {}
                if isinstance(meta, str):
                    meta = json.loads(meta)
                if meta.get("connector_type"):
                    datasources.append(
                        {
                            "id": str(row["uuid"]),
                            "name": row["name"],
                            "meta": meta,
                        }
                    )
    logger.info("Step 3: Found %d datasources with connector info", len(datasources))

    # ------------------------------------------------------------------ #
    # 4.  Check Airbyte health
    # ------------------------------------------------------------------ #
    import httpx

    async with httpx.AsyncClient(base_url=AIRBYTE_API_URL, timeout=30.0) as client:
        try:
            resp = await client.post("/health")
            if resp.status_code == 200:
                logger.info("Step 4: Airbyte API is healthy ✅")
            else:
                logger.warning(
                    "Step 4: Airbyte API returned %d — continuing anyway", resp.status_code
                )
        except Exception as e:
            logger.error("Step 4: Cannot reach Airbyte API: %s", e)
            logger.error("Make sure Airbyte OSS is running. Aborting.")
            sys.exit(1)

    # ------------------------------------------------------------------ #
    # 5.  Check existing mappings
    # ------------------------------------------------------------------ #
    existing_mappings: set[str] = set()
    async with await psycopg.AsyncConnection.connect(DATABASE_URI) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT datasource_id FROM datasource_airbyte_mapping")
            rows = await cur.fetchall()
            existing_mappings = {str(r["datasource_id"]) for r in rows}
    logger.info("Step 5: %d datasources already migrated", len(existing_mappings))

    # ------------------------------------------------------------------ #
    # 6.  Migrate each datasource
    # ------------------------------------------------------------------ #
    migrated = 0
    skipped = 0
    failed = 0

    for ds in datasources:
        ds_id = ds["id"]

        if ds_id in existing_mappings:
            logger.info("  ⏭️  %s (%s) — already migrated", ds["name"], ds_id)
            skipped += 1
            continue

        logger.info("  🔄 Migrating %s (%s)...", ds["name"], ds_id)
        meta = ds["meta"]
        connector_type = meta.get("connector_type", "")
        connector_config = meta.get("connector_config", {})

        if not connector_type or not connector_config:
            logger.warning("     ⚠️  No connector config stored — skipping")
            skipped += 1
            continue

        try:
            async with httpx.AsyncClient(base_url=AIRBYTE_API_URL, timeout=60.0) as client:
                # Get workspace
                ws_resp = await client.post("/workspaces/list")
                ws_data = ws_resp.json()
                workspace_id = ws_data["workspaces"][0]["workspaceId"]

                # Find source definition by name
                sd_resp = await client.post(
                    "/source_definitions/list",
                    json={"workspaceId": workspace_id},
                )
                sd_data = sd_resp.json()
                source_def = None
                for sd in sd_data.get("sourceDefinitions", []):
                    if sd["name"].lower().replace(" ", "-") == connector_type.lower().replace(
                        "source-", ""
                    ):
                        source_def = sd
                        break
                    if connector_type in sd.get("name", "").lower():
                        source_def = sd
                        break

                if not source_def:
                    logger.warning("     ⚠️  Source definition not found for '%s'", connector_type)
                    failed += 1
                    continue

                # Create Airbyte source
                src_resp = await client.post(
                    "/sources/create",
                    json={
                        "workspaceId": workspace_id,
                        "sourceDefinitionId": source_def["sourceDefinitionId"],
                        "connectionConfiguration": connector_config,
                        "name": f"{ds['name']} (migrated)",
                    },
                )
                if src_resp.status_code != 200:
                    logger.warning("     ❌ Failed to create source: %s", src_resp.text[:200])
                    failed += 1
                    continue
                source_data = src_resp.json()
                source_id = source_data["sourceId"]

                # Get or create default destination
                dst_resp = await client.post(
                    "/destinations/list",
                    json={"workspaceId": workspace_id},
                )
                dst_data = dst_resp.json()
                destinations = dst_data.get("destinations", [])
                local_json_dst = None
                for d in destinations:
                    if (
                        "local" in d.get("destinationName", "").lower()
                        and "json" in d.get("destinationName", "").lower()
                    ):
                        local_json_dst = d
                        break

                if not local_json_dst:
                    # Create local-json destination
                    dd_resp = await client.post(
                        "/destination_definitions/list",
                        json={"workspaceId": workspace_id},
                    )
                    dd_data = dd_resp.json()
                    local_json_def = None
                    for dd in dd_data.get("destinationDefinitions", []):
                        if "local" in dd["name"].lower() and "json" in dd["name"].lower():
                            local_json_def = dd
                            break

                    if local_json_def:
                        dst_create = await client.post(
                            "/destinations/create",
                            json={
                                "workspaceId": workspace_id,
                                "destinationDefinitionId": local_json_def[
                                    "destinationDefinitionId"
                                ],
                                "connectionConfiguration": {
                                    "destination_path": "/tmp/airbyte_local"
                                },
                                "name": "Local JSON (agent-service)",
                            },
                        )
                        local_json_dst = dst_create.json()

                if not local_json_dst:
                    logger.warning("     ❌ Could not create local-json destination")
                    failed += 1
                    continue

                dest_id = local_json_dst.get("destinationId", "")

                # Discover schema
                disc_resp = await client.post(
                    "/sources/discover_schema",
                    json={"sourceId": source_id},
                )
                catalog = disc_resp.json().get("catalog", {})

                # Build sync catalog
                streams_config = []
                for stream_entry in catalog.get("streams", []):
                    stream = stream_entry.get("stream", {})
                    streams_config.append(
                        {
                            "stream": stream,
                            "config": {
                                "syncMode": "full_refresh",
                                "destinationSyncMode": "overwrite",
                                "selected": True,
                            },
                        }
                    )

                # Create connection
                conn_body: dict = {
                    "sourceId": source_id,
                    "destinationId": dest_id,
                    "syncCatalog": {"streams": streams_config},
                    "status": "active",
                    "name": f"{ds['name']}",
                }

                # Apply schedule from old sync_schedules if available
                old_sched = old_schedules.get(ds_id)
                if old_sched and old_sched.get("enabled"):
                    conn_body["scheduleType"] = "cron"
                    conn_body["scheduleData"] = {
                        "cron": {
                            "cronExpression": old_sched.get("cron_expression", "0 0 0 * * ?"),
                            "cronTimeZone": old_sched.get("timezone", "UTC"),
                        }
                    }
                else:
                    conn_body["scheduleType"] = "manual"

                conn_resp = await client.post("/connections/create", json=conn_body)
                if conn_resp.status_code != 200:
                    logger.warning("     ❌ Failed to create connection: %s", conn_resp.text[:200])
                    failed += 1
                    continue
                conn_data = conn_resp.json()
                connection_id = conn_data["connectionId"]

                # Insert mapping
                update_graph = old_sched.get("update_graph_rag", False) if old_sched else False
                async with await psycopg.AsyncConnection.connect(DATABASE_URI) as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            """
                            INSERT INTO datasource_airbyte_mapping
                                (datasource_id, airbyte_source_id, airbyte_connection_id,
                                 airbyte_destination_id, update_graph_rag)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (datasource_id) DO UPDATE SET
                                airbyte_source_id = EXCLUDED.airbyte_source_id,
                                airbyte_connection_id = EXCLUDED.airbyte_connection_id,
                                airbyte_destination_id = EXCLUDED.airbyte_destination_id,
                                update_graph_rag = EXCLUDED.update_graph_rag,
                                updated_at = NOW()
                            """,
                            (ds_id, source_id, connection_id, dest_id, update_graph),
                        )
                    await conn.commit()

                logger.info(
                    "     ✅ Migrated — source=%s connection=%s",
                    source_id[:8],
                    connection_id[:8],
                )
                migrated += 1

        except Exception as e:
            logger.error("     ❌ Error: %s", e)
            failed += 1

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    logger.info("")
    logger.info("=" * 50)
    logger.info("Migration complete!")
    logger.info("  Migrated: %d", migrated)
    logger.info("  Skipped:  %d", skipped)
    logger.info("  Failed:   %d", failed)
    logger.info("=" * 50)

    if failed > 0:
        logger.warning(
            "Some datasources failed to migrate. You can re-run this script "
            "to retry — already-migrated datasources will be skipped."
        )

    # ------------------------------------------------------------------ #
    # 7.  Optional: Drop old sync_schedules table
    # ------------------------------------------------------------------ #
    if old_schedules:
        logger.info("")
        logger.info(
            "Old sync_schedules table still exists with %d rows.",
            len(old_schedules),
        )
        logger.info("You can drop it manually after verifying the migration:")
        logger.info("  DROP TABLE IF EXISTS sync_schedules;")


if __name__ == "__main__":
    asyncio.run(main())
