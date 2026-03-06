"""
Airbyte REST API Client.

Async HTTP client wrapping all Airbyte REST API v1 endpoints needed by
agent-service.  This is the **single integration layer** between
agent-service and the Airbyte OSS platform.

All methods are async using ``httpx.AsyncClient`` with connection pooling,
retry, and timeout handling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class AirbyteAPIError(Exception):
    """Raised when the Airbyte REST API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"Airbyte API error {status_code}: {message}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AirbyteAPIClient:
    """Async wrapper around the Airbyte REST API v1."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("AIRBYTE_API_URL", "http://airbyte-server:8001/api/v1")
        ).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._workspace_id: str | None = None

    # ---- lifecycle -------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=10.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Shut down the underlying HTTP connection pool."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ---- low-level request with retry ------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send a request with exponential-backoff retry on 5xx / connection errors."""
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await client.request(
                    method,
                    path,
                    json=json or {},
                    timeout=timeout or self._timeout,
                )
                if resp.status_code >= 400:
                    body = resp.text[:500]
                    if resp.status_code >= 500 and attempt < self._max_retries:
                        delay = 2 ** (attempt - 1)
                        logger.warning(
                            "Airbyte API %s %s returned %d (attempt %d/%d), retrying in %ds",
                            method, path, resp.status_code, attempt, self._max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise AirbyteAPIError(resp.status_code, body)
                return resp.json() if resp.text else {}
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = 2 ** (attempt - 1)
                    logger.warning(
                        "Airbyte API connection error on %s %s (attempt %d/%d): %s — retrying in %ds",
                        method, path, attempt, self._max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise AirbyteAPIError(0, f"Connection failed after {self._max_retries} attempts: {exc}") from exc

        # Should not reach here, but just in case
        raise AirbyteAPIError(0, f"Request failed: {last_exc}")

    async def _post(self, path: str, json: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        return await self._request("POST", path, json, **kw)

    # ---- workspace -------------------------------------------------------

    async def get_workspace_id(self) -> str:
        """Fetch the default workspace UUID (cached after first call)."""
        if self._workspace_id:
            return self._workspace_id

        data = await self._post("/workspaces/list")
        workspaces = data.get("workspaces", [])
        if not workspaces:
            raise AirbyteAPIError(404, "No Airbyte workspaces found")

        self._workspace_id = workspaces[0]["workspaceId"]
        logger.info("Using Airbyte workspace: %s", self._workspace_id)
        return self._workspace_id

    # ---- source definitions (connector discovery) ------------------------

    async def list_source_definitions(self) -> list[dict[str, Any]]:
        """List all available connector types."""
        workspace_id = await self.get_workspace_id()
        data = await self._post(
            "/source_definitions/list_for_workspace",
            {"workspaceId": workspace_id},
        )
        return data.get("sourceDefinitions", [])

    async def get_source_definition_spec(self, source_definition_id: str) -> dict[str, Any]:
        """Get raw JSON Schema spec for a connector type.

        Returns the raw ``connectionSpecification`` — **NO** flattening,
        **NO** transformation.  The frontend handles all rendering complexity
        via the recursive SchemaForm.
        """
        workspace_id = await self.get_workspace_id()
        data = await self._post(
            "/source_definition_specifications/get",
            {
                "sourceDefinitionId": source_definition_id,
                "workspaceId": workspace_id,
            },
        )
        return data

    # ---- sources ---------------------------------------------------------

    async def create_source(
        self,
        name: str,
        source_definition_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a source instance with user-provided config."""
        workspace_id = await self.get_workspace_id()
        return await self._post(
            "/sources/create",
            {
                "workspaceId": workspace_id,
                "sourceDefinitionId": source_definition_id,
                "name": name,
                "connectionConfiguration": config,
            },
        )

    async def check_source_connection(self, source_id: str) -> dict[str, Any]:
        """Test if source credentials and config are valid."""
        return await self._post(
            "/sources/check_connection",
            {"sourceId": source_id},
            timeout=120.0,
        )

    async def discover_source_schema(self, source_id: str) -> dict[str, Any]:
        """Discover available streams/tables from a source."""
        return await self._post(
            "/sources/discover_schema",
            {"sourceId": source_id},
            timeout=120.0,
        )

    async def delete_source(self, source_id: str) -> None:
        """Delete a source."""
        await self._post("/sources/delete", {"sourceId": source_id})

    async def get_source(self, source_id: str) -> dict[str, Any]:
        """Get a source by ID."""
        return await self._post("/sources/get", {"sourceId": source_id})

    # ---- destinations ----------------------------------------------------

    async def create_destination(
        self,
        name: str,
        destination_definition_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a destination instance."""
        workspace_id = await self.get_workspace_id()
        return await self._post(
            "/destinations/create",
            {
                "workspaceId": workspace_id,
                "destinationDefinitionId": destination_definition_id,
                "name": name,
                "connectionConfiguration": config,
            },
        )

    async def list_destinations(self) -> list[dict[str, Any]]:
        """List all destinations in the workspace."""
        workspace_id = await self.get_workspace_id()
        data = await self._post(
            "/destinations/list",
            {"workspaceId": workspace_id},
        )
        return data.get("destinations", [])

    async def list_destination_definitions(self) -> list[dict[str, Any]]:
        """List all destination definitions."""
        workspace_id = await self.get_workspace_id()
        data = await self._post(
            "/destination_definitions/list_for_workspace",
            {"workspaceId": workspace_id},
        )
        return data.get("destinationDefinitions", [])

    async def get_or_create_default_destination(self) -> str:
        """Ensure a default local-json destination exists, return its ID.

        Called during datasource creation.  Creates once, reuses for all
        connections thereafter.
        """
        destinations = await self.list_destinations()
        for dest in destinations:
            if dest.get("name") == "agent-service-local-json":
                logger.info("Reusing existing default destination: %s", dest["destinationId"])
                return dest["destinationId"]

        # Find the Local JSON destination definition
        definitions = await self.list_destination_definitions()
        local_json_def = None
        for defn in definitions:
            docker_repo = defn.get("dockerRepository", "")
            if "destination-local-json" in docker_repo:
                local_json_def = defn
                break

        if not local_json_def:
            raise AirbyteAPIError(
                404,
                "Local JSON destination definition not found in Airbyte. "
                "Ensure Airbyte OSS is properly initialized.",
            )

        # destination_path is relative to /local inside the connector container.
        # /local is mapped to LOCAL_ROOT on the worker (/tmp/airbyte_local on host).
        # Use "/" so files land directly in /tmp/airbyte_local/<stream>.jsonl,
        # NOT /tmp/airbyte_local/tmp/airbyte_local/<stream>.jsonl (double nesting).
        dest = await self.create_destination(
            name="agent-service-local-json",
            destination_definition_id=local_json_def["destinationDefinitionId"],
            config={"destination_path": "/"},
        )
        logger.info("Created default local-json destination: %s", dest["destinationId"])
        return dest["destinationId"]

    # ---- connections -----------------------------------------------------

    async def create_connection(
        self,
        source_id: str,
        destination_id: str,
        streams: list[dict[str, Any]] | None = None,
        schedule: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Create a source → destination connection, optionally with cron schedule."""
        payload: dict[str, Any] = {
            "sourceId": source_id,
            "destinationId": destination_id,
            "status": "active",
            "namespaceDefinition": "source",
            "namespaceFormat": "${SOURCE_NAMESPACE}",
            "prefix": "",
        }

        if name:
            payload["name"] = name

        # Configure sync catalog
        if streams:
            payload["syncCatalog"] = {"streams": streams}

        # Configure schedule
        if schedule:
            payload["scheduleType"] = "cron"
            payload["scheduleData"] = {
                "cron": {
                    "cronExpression": schedule.get("cronExpression", "0 0 * * * ?"),
                    "cronTimeZone": schedule.get("cronTimeZone", "UTC"),
                }
            }
        else:
            payload["scheduleType"] = "manual"

        return await self._post("/connections/create", payload)

    async def update_connection(
        self,
        connection_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update connection fields."""
        payload: dict[str, Any] = {"connectionId": connection_id}
        payload.update(fields)
        return await self._post("/connections/update", payload)

    async def update_connection_schedule(
        self,
        connection_id: str,
        schedule: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Update or disable schedule on an existing connection.

        ``schedule=None`` sets scheduleType to 'manual' (disables scheduling).

        Accepts the nested structure produced by schedule_routes.
        Cron expressions are expected in 6-field Quartz format.
        """
        if schedule:
            # Extract cron data from the nested structure
            cron_data = (
                schedule.get("scheduleData", {}).get("cron", {})
            )
            cron_expr = cron_data.get("cronExpression", "0 0 0 * * ?")
            tz = cron_data.get("cronTimeZone", "UTC")

            return await self.update_connection(
                connection_id,
                scheduleType="cron",
                scheduleData={
                    "cron": {
                        "cronExpression": cron_expr,
                        "cronTimeZone": tz,
                    }
                },
            )
        else:
            return await self.update_connection(
                connection_id,
                scheduleType="manual",
                scheduleData=None,
            )

    async def get_connection(self, connection_id: str) -> dict[str, Any]:
        """Get a connection by ID."""
        return await self._post("/connections/get", {"connectionId": connection_id})

    async def delete_connection(self, connection_id: str) -> None:
        """Delete a connection."""
        await self._post("/connections/delete", {"connectionId": connection_id})

    # ---- sync / jobs -----------------------------------------------------

    async def trigger_sync(self, connection_id: str) -> dict[str, Any]:
        """Trigger a manual sync for a connection."""
        return await self._post("/connections/sync", {"connectionId": connection_id})

    async def get_job(self, job_id: int) -> dict[str, Any]:
        """Get single job status."""
        return await self._post("/jobs/get", {"id": job_id})

    async def list_jobs(
        self,
        config_id: str,
        config_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """List recent jobs for a connection."""
        payload: dict[str, Any] = {
            "configId": config_id,
            "configTypes": config_types or ["sync"],
            "pagination": {"pageSize": limit, "rowOffset": 0},
        }
        data = await self._post("/jobs/list", payload)
        return data.get("jobs", [])

    async def poll_job_until_complete(
        self,
        job_id: int,
        poll_interval: float = 5.0,
        timeout: float = 3600.0,
    ) -> dict[str, Any]:
        """Wait for a sync job to reach a terminal state.

        Terminal statuses: succeeded, failed, cancelled.
        Active statuses:   pending, running, incomplete.
        """
        terminal = {"succeeded", "failed", "cancelled"}
        elapsed = 0.0

        while elapsed < timeout:
            data = await self.get_job(job_id)
            job = data.get("job", data)
            status = job.get("status", "unknown")

            if status in terminal:
                logger.info("Airbyte job %d reached terminal status: %s", job_id, status)
                return data

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise AirbyteAPIError(
            408, f"Job {job_id} did not complete within {timeout}s"
        )

    # ---- health ----------------------------------------------------------

    async def health_check(self) -> bool:
        """Return True if Airbyte API is reachable."""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code < 500
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_INSTANCE: AirbyteAPIClient | None = None


def get_airbyte_client() -> AirbyteAPIClient:
    """Return the global AirbyteAPIClient singleton (creates lazily)."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AirbyteAPIClient()
    return _INSTANCE
