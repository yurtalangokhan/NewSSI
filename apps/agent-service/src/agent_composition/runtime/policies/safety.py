"""Safety policy using the RuntimePolicy protocol.

The SafetyPolicy implements the RuntimePolicy contract for pre-run input
moderation and post-run output moderation. It wraps any existing guard
behavior without creating a duplicate guarded-brain abstraction.

The guard failure policy is recorded as: fail-closed (block request)
when guard moderation fails, with telemetry. This decision is based on
the design.md open-questions section which deferred this decision to ASC-1.
The default behavior follows the existing guard implementation which
raises on moderation failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_composition.domain.ports import (
    RuntimePolicyDecision,
    RuntimePolicyRequest,
    RuntimePolicyResult,
)
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SafetyPolicyConfig:
    """Configuration for the safety policy."""

    enabled: bool = False
    # Guard model key to use for moderation.
    guard_model_key: str | None = None
    # Fail-open allows requests through when guard fails (default: False = fail-closed).
    fail_open: bool = False


class SafetyPolicy:
    """Pre-run input and post-run output moderation policy.

    This policy implements the RuntimePolicy protocol. It wraps the existing
    guard (moderation) behavior that was embedded in LazyLoadingAgent subclasses.

    Guard failure policy: fail-closed by default. When moderation fails,
    the request is blocked and a RuntimePolicyDecision with continue_run=False
    is returned. Set fail_open=True in config to allow requests through on
    guard failure (not recommended for production with sensitive data).
    """

    key: str = "safety"

    def __init__(self, config: SafetyPolicyConfig | None = None) -> None:
        self._config = config or SafetyPolicyConfig()

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    async def before_run(self, request: RuntimePolicyRequest) -> RuntimePolicyDecision:
        """Moderate the input before agent execution.

        Currently a no-op stub. Real implementation requires a guard model
        provider. Until then, this returns continue_run=True.
        """
        if not self._config.enabled:
            return RuntimePolicyDecision(continue_run=True, reason="safety disabled")

        try:
            # Placeholder for actual guard moderation.
            # Real implementation would call a guard model here.
            # Until guard model exists, always allow.
            return RuntimePolicyDecision(continue_run=True, reason="guard placeholder")
        except Exception as exc:
            logger.warning("[SafetyPolicy] Guard check failed: %s", exc)
            if self._config.fail_open:
                return RuntimePolicyDecision(
                    continue_run=True,
                    reason=f"guard failed, fail-open: {exc}",
                    metadata={"error": str(exc)},
                )
            return RuntimePolicyDecision(
                continue_run=False,
                reason=f"guard blocked: {exc}",
                metadata={"error": str(exc)},
            )

    async def after_run(self, request: RuntimePolicyRequest, result: Any) -> RuntimePolicyResult:
        """Moderate the output after agent execution.

        Currently a no-op stub. Real implementation requires a guard model
        provider for output content moderation.
        """
        if not self._config.enabled:
            return RuntimePolicyResult(metadata={"skipped": "safety disabled"})

        try:
            # Placeholder for actual output guard moderation.
            return RuntimePolicyResult(metadata={"skipped": "guard placeholder"})
        except Exception as exc:
            logger.warning("[SafetyPolicy] Output guard check failed: %s", exc)
            if self._config.fail_open:
                return RuntimePolicyResult(metadata={"error": str(exc), "fail_open": True})
            return RuntimePolicyResult(metadata={"error": str(exc), "blocked": True})

    async def close(self) -> None:
        """Safety policy has no persistent resources to close."""
        pass
