"""Idempotency configuration for the FastMCP HTTP transport."""

from config_manager import ConfigManager
from idempotency import (
    IdempotencyConfig,
    IdempotencyMode,
    IdempotencyPolicy,
    IdempotencyPolicyConfig,
)
from metrics import install_idempotency_recorder

from src.core.idempotency_principal import extract_principal_from_jwt


def build_idempotency_config(settings: ConfigManager) -> IdempotencyConfig:
    """Build the shared idempotency middleware config for tools-service."""
    return IdempotencyConfig(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        redis_db=settings.REDIS_DB,
        redis_password=settings.REDIS_PASSWORD,
        idempotency_ttl=settings.IDEMPOTENCY_TTL,
        idempotency_enabled=settings.IDEMPOTENCY_ENABLED,
        lock_ttl=settings.IDEMPOTENCY_LOCK_TTL,
        wait_timeout=settings.IDEMPOTENCY_WAIT_TIMEOUT,
        service_name="tools-service",
        decision_recorder=install_idempotency_recorder("tools-service"),
        principal_extractor=extract_principal_from_jwt,
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
