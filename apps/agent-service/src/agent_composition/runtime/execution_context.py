"""Separation of model-visible and trusted execution context.

Trusted values (user identity, tenant, binding references, attachment
handles, project ID, request ID) never enter prompts or model-visible
tool schemas. They are carried through the invocation envelope only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from agent_composition.domain.ports import TrustedToolContext

# Reserved keys that must not appear in model-visible arguments.
RESERVED_CONTEXT_KEYS = frozenset(
    {
        "user_id",
        "tenant_id",
        "binding_references",
        "attachment_handles",
        "project_id",
        "request_id",
        "internal_auth",
    }
)


@dataclass(frozen=True)
class AgentExecutionContext:
    """Request-scoped execution values extracted from the LangGraph RunnableConfig.

    This carries values parsed from the ``configurable`` block of a
    RunnableConfig. It is the single source of truth for user/tenant/project
    identity during a single agent invocation.
    """

    user_id: str | None = None
    tenant_id: str | None = None
    binding_references: Mapping[str, str] = field(default_factory=dict)
    attachment_handles: tuple[str, ...] = ()
    project_id: str | None = None
    request_id: str | None = None
    thread_id: str | None = None
    checkpoint_ns: str | None = None
    # Raw configurable block for policy extension.
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runnable_config(cls, config: dict[str, Any] | None) -> AgentExecutionContext:
        """Extract execution context from a LangGraph RunnableConfig."""
        if config is None:
            return cls()
        configurable = config.get("configurable") or {}
        return cls(
            user_id=configurable.get("user_id"),
            tenant_id=configurable.get("tenant_id"),
            binding_references=configurable.get("binding_references") or {},
            attachment_handles=tuple(
                a.get("handle") or a.get("filename") or ""
                for a in (configurable.get("mail_attachments") or [])
                if a
            ),
            project_id=configurable.get("project_id"),
            request_id=configurable.get("request_id"),
            thread_id=configurable.get("thread_id"),
            checkpoint_ns=configurable.get("checkpoint_ns"),
            extra=configurable,
        )

    def to_trusted_context(self) -> TrustedToolContext:
        """Convert to the domain TrustedToolContext for tool invocation."""
        return TrustedToolContext(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            binding_references=self.binding_references,
            attachment_handles=self.attachment_handles,
            project_id=self.project_id,
            request_id=self.request_id,
        )

    def is_trusted(self) -> bool:
        """Return True if at least one trusted value is present."""
        return bool(
            self.user_id
            or self.tenant_id
            or self.binding_references
            or self.attachment_handles
            or self.project_id
            or self.request_id
        )


@dataclass(frozen=True)
class TrustedExecutionContext:
    """Immutable trusted context for internal service calls.

    This wraps an AgentExecutionContext and guarantees that only
    trusted (non-model-visible) values are accessible. It is passed
    to tool adapters for constructing transport headers and internal
    envelope fields.
    """

    inner: AgentExecutionContext

    @property
    def user_id(self) -> str | None:
        return self.inner.user_id

    @property
    def tenant_id(self) -> str | None:
        return self.inner.tenant_id

    @property
    def binding_references(self) -> Mapping[str, str]:
        return self.inner.binding_references

    @property
    def attachment_handles(self) -> tuple[str, ...]:
        return self.inner.attachment_handles

    @property
    def project_id(self) -> str | None:
        return self.inner.project_id

    @property
    def request_id(self) -> str | None:
        return self.inner.request_id

    def is_available(self) -> bool:
        """Return True if trusted context is populated."""
        return self.inner.is_trusted()
