"""Runtime package for composed agent execution.

This package provides the composed runtime contract that replaces the
multi-responsibility LazyLoadingAgent base class with explicit,
composed components for lifecycle, checkpoint, memory, safety, retry,
and execution context.
"""

from .checkpoint import CheckpointAdapter
from .composed_agent import ComposedAgent
from .execution_context import AgentExecutionContext, TrustedExecutionContext
from .lifecycle import AgentLifecycle, IdempotentLifecycle
from .policies.memory import MemoryPolicy, MemoryPolicyConfig
from .policies.retry import RetryPolicy, RetryPolicyConfig
from .policies.safety import SafetyPolicy, SafetyPolicyConfig

__all__ = [
    "ComposedAgent",
    "AgentExecutionContext",
    "TrustedExecutionContext",
    "AgentLifecycle",
    "IdempotentLifecycle",
    "CheckpointAdapter",
    "MemoryPolicy",
    "MemoryPolicyConfig",
    "SafetyPolicy",
    "SafetyPolicyConfig",
    "RetryPolicy",
    "RetryPolicyConfig",
]
