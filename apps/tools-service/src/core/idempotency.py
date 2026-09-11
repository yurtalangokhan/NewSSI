"""Idempotency configuration for the FastMCP HTTP transport."""

from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)

from src.core.settings import Settings


def build_idempotency_config(settings: Settings) -> IdempotencyConfig:
    """Build the shared idempotency middleware config for tools-service."""
    return IdempotencyConfig(
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
        redis_db=settings.redis_db,
        redis_password=settings.redis_password,
        idempotency_ttl=settings.idempotency_ttl,
        idempotency_enabled=settings.idempotency_enabled,
        service_name="tools-service",
        enforce_required_keys=settings.idempotency_enforce_required_keys,
        lock_ttl=settings.idempotency_lock_ttl,
        wait_timeout=settings.idempotency_wait_timeout,
        policy=build_idempotency_policy(),
    )


def build_idempotency_exclude_paths() -> set[str]:
    """Build public paths that bypass idempotency handling."""
    return {"/health", "/health/ready"}


def build_idempotency_policy() -> IdempotencyPolicyConfig:
    """Build route-level idempotency policy for tools-service.

    ``/mcp`` stays classified as DOMAIN_REQUIRED for the middleware contract,
    but does NOT enforce a missing key. MCP streamable-HTTP sessions issue many
    POSTs (initialize, tools/list, tools/call) that all share the client's
    connection headers, so a static Idempotency-Key cannot represent a single
    logical operation. Requiring one would 400 every legitimate MCP client,
    including agent-service's MultiServerMCPClient.
    """
    return IdempotencyPolicyConfig(
        default_mode=IdempotencyMode.OPTIONAL_REPLAY,
        route_policies=[
            IdempotencyPolicy(
                method="POST",
                path="/mcp",
                mode=IdempotencyMode.DOMAIN_REQUIRED,
                enforce_missing_key=False,
            ),
        ],
    )
