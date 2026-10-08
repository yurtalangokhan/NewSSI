"""ComposedAgent — explicit runtime contract with separated concerns.

ComposedAgent replaces the multi-responsibility LazyLoadingAgent base class
with explicit, composed components for:

- lifecycle (load/close)
- checkpoint (state management)
- memory policy (post-run extraction/persistence)
- safety policy (pre/post moderation via RuntimePolicy)
- retry policy (timeout and retry via RuntimePolicy)
- execution context (trusted user/tenant identity)

Callers depend on this interface instead of checking concrete
LazyLoadingAgent types or private fields.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextvars import ContextVar
from typing import Any

from langchain_core.runnables import RunnableConfig

from agent_composition.domain.definitions import RuntimePolicyConfig
from agent_composition.domain.ports import (
    AgentChunk,
    AgentEvent,
    AgentRunRequest,
    AgentRunResult,
    AgentState,
    ExecutableAgent,
    RuntimePolicy,
    RuntimePolicyRequest,
    StateRequest,
    StateUpdateRequest,
)
from core.observability.logger import get_logger
from memory.recall import (
    build_memory_recall_event,
    inject_memory_into_input,
    mark_input_with_ltm_recalled,
    resolve_langgraph_store,
    tag_output_with_recalled_memories,
)

from .execution_context import AgentExecutionContext, TrustedExecutionContext
from .lifecycle import IdempotentLifecycle
from .policies import (
    MemoryPolicy,
    MemoryPolicyConfig,
    RetryPolicy,
    RetryPolicyConfig,
    SafetyPolicy,
    SafetyPolicyConfig,
)

logger = get_logger(__name__)

# Context variable for trusted context at invocation time.
_trusted_context_var: ContextVar[TrustedExecutionContext | None] = ContextVar("_trusted_context_var", default=None)


def get_trusted_context() -> TrustedExecutionContext | None:
    """Read the current trusted execution context from the context variable."""
    return _trusted_context_var.get()


class ComposedAgent(ExecutableAgent, IdempotentLifecycle):
    """Composed runtime with explicit lifecycle and policy components.

    ComposedAgent is the sole owner of acquired runtime resources. Its
    idempotent load() method acquires them in order; its idempotent
    close() releases them in reverse order.

    Runtime policies (memory, safety, retry) are applied around each
    run operation through the RuntimePolicy protocol.

    This class maintains full backward compatibility with the
    LazyLoadingAgent interface so existing callers do not break.
    """

    def __init__(
        self,
        executable_agent: ExecutableAgent | None = None,
        runtime_policy_config: RuntimePolicyConfig | None = None,
        checkpointer: Any | None = None,
        memory_policy: MemoryPolicy | None = None,
        safety_policy: SafetyPolicy | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        """
        Args:
            executable_agent: The pre-built ExecutableAgent (from a GraphSchemaStrategy.build() call).
                This is the primary construction path — the caller builds the graph
                via a strategy and passes the result here.
            runtime_policy_config: Runtime policy configuration (used if policies not provided).
            checkpointer: Optional LangGraph checkpointer for state persistence.
            memory_policy: Optional memory policy (MemoryPolicyConfig used if not provided).
            safety_policy: Optional safety policy (SafetyPolicyConfig used if not provided).
            retry_policy: Optional retry policy (RetryPolicyConfig used if not provided).
        """
        IdempotentLifecycle.__init__(self)
        self._executable_agent: ExecutableAgent | None = executable_agent
        self._policy_config = runtime_policy_config or RuntimePolicyConfig()
        self._checkpointer = checkpointer

        # Initialize policies from config or create defaults.
        self._memory_policy = memory_policy or self._build_memory_policy()
        self._safety_policy = safety_policy or self._build_safety_policy()
        self._retry_policy = retry_policy or self._build_retry_policy()

    # ------------------------------------------------------------------
    # Policy builders (can be overridden in subclass for custom policy)
    # ------------------------------------------------------------------

    def _build_memory_policy(self) -> MemoryPolicy:
        cfg = self._policy_config.memory or {}
        return MemoryPolicy(
            MemoryPolicyConfig(
                enabled=cfg.get("enabled", False),
                extract_memory=cfg.get("extract_memory", True),
            )
        )

    def _build_safety_policy(self) -> SafetyPolicy:
        cfg = self._policy_config.safety or {}
        return SafetyPolicy(
            SafetyPolicyConfig(
                enabled=cfg.get("enabled", False),
                fail_open=cfg.get("fail_open", False),
            )
        )

    def _build_retry_policy(self) -> RetryPolicy:
        cfg = self._policy_config.retry or {}
        return RetryPolicy(
            RetryPolicyConfig(
                enabled=cfg.get("enabled", False),
                max_attempts=cfg.get("max_attempts", 2),
                initial_delay=cfg.get("initial_delay", 0.5),
                max_delay=cfg.get("max_delay", 5.0),
                timeout_seconds=cfg.get("timeout_seconds", 0),
            )
        )

    # ------------------------------------------------------------------
    # Lifecycle (IdempotentLifecycle)
    # ------------------------------------------------------------------

    async def load(self) -> None:
        """Mark the agent as loaded.

        The executable agent is expected to already be built by the caller
        (e.g., AgentComposer) before ComposedAgent is constructed.
        This method is idempotent and validates the pre-built agent is present.
        """
        if self._loaded:
            return

        if self._executable_agent is None:
            raise RuntimeError(
                "ComposedAgent.load() called without a pre-built ExecutableAgent. "
                "Construct ComposedAgent with executable_agent set."
            )

        self._loaded = True
        logger.info("ComposedAgent loaded.")

    async def close(self) -> None:
        """Release all runtime resources in reverse dependency order.

        Closing is idempotent. If already closed, this is a no-op.
        """
        if not self._loaded:
            return

        # Close policies in reverse order.
        await self._retry_policy.close()
        await self._safety_policy.close()
        await self._memory_policy.close()

        # Close the executable agent if it has a close method.
        if self._executable_agent is not None and hasattr(self._executable_agent, "close"):
            await self._executable_agent.close()

        self._loaded = False
        logger.info("ComposedAgent closed.")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def executable_agent(self) -> ExecutableAgent | None:
        """The wrapped executable runtime, exposed for composition tests."""
        return self._executable_agent

    # ------------------------------------------------------------------
    # Execution context helpers
    # ------------------------------------------------------------------

    def _get_execution_context(self, config: RunnableConfig | None) -> AgentExecutionContext:
        """Extract execution context from the runnable config."""
        return AgentExecutionContext.from_runnable_config(config or {})

    def _get_trusted_context(self, config: RunnableConfig | None) -> TrustedExecutionContext | None:
        """Build trusted execution context from runnable config."""
        ctx = self._get_execution_context(config)
        if not ctx.is_trusted():
            return None
        return TrustedExecutionContext(inner=ctx)

    # ------------------------------------------------------------------
    # Memory hooks (mirrors LazyLoadingAgent._inject_memory_into_input)
    # ------------------------------------------------------------------

    def _get_langgraph_store(self):
        """Get the global LangGraph store for long-term memory."""
        return resolve_langgraph_store()

    def _build_memory_recall_event(self, memories: dict[str, Any]) -> dict[str, Any] | None:
        """Build a custom stream event payload for recalled memories."""
        return build_memory_recall_event(memories)

    def _mark_input_with_ltm_recalled(self, input: Any, recalled_count: int) -> Any:
        """Attach recalled-memory count to the latest user message."""
        return mark_input_with_ltm_recalled(input, recalled_count)

    def _tag_output_with_recalled_memories(self, output: Any, memories: dict[str, Any]) -> Any:
        """Tag response messages so chat history can replay memory recall."""
        return tag_output_with_recalled_memories(output, memories)

    async def _inject_memory_into_input(
        self,
        input: Any,
        config: RunnableConfig | None = None,
    ) -> tuple[Any, dict, str | None]:
        """Recall long-term memories and prepend them to *input*."""
        return await inject_memory_into_input(input, config)

    # ------------------------------------------------------------------
    # Runnable passthrough (checkpoint delegation)
    # ------------------------------------------------------------------

    async def aget_state(self, request: StateRequest) -> AgentState:
        """Get the current agent state from the underlying graph."""
        await self.ensure_loaded()
        # Delegate to checkpoint adapter via the graph.
        # For now, delegate to the built agent if available.
        if self._executable_agent is not None:
            return await self._executable_agent.aget_state(request)
        raise NotImplementedError("ComposedAgent.aget_state requires a built graph agent")

    async def aupdate_state(self, request: StateUpdateRequest) -> AgentState:
        """Update the current agent state in the underlying graph."""
        await self.ensure_loaded()
        if self._executable_agent is not None:
            return await self._executable_agent.aupdate_state(request)
        raise NotImplementedError("ComposedAgent.aupdate_state requires a built graph agent")

    async def aget_state_history(self, request: StateRequest) -> AsyncIterator[AgentState]:
        """Iterate over the agent state history from the underlying graph."""
        await self.ensure_loaded()
        if self._executable_agent is not None:
            async for snapshot in self._executable_agent.aget_state_history(request):
                yield snapshot
        else:
            raise NotImplementedError("ComposedAgent.aget_state_history requires a built graph agent")

    # ------------------------------------------------------------------
    # Runtime policy application helpers
    # ------------------------------------------------------------------

    async def _apply_before_run_policies(self, policy_request: RuntimePolicyRequest) -> None:
        """Apply all before-run RuntimePolicy instances; raise if any blocks."""
        for policy in [self._safety_policy, self._retry_policy]:
            if isinstance(policy, RuntimePolicy):
                decision = await policy.before_run(policy_request)
                if not decision.continue_run:
                    raise RuntimeError(f"Policy {policy.key} blocked run: {decision.reason}")

    async def _apply_after_run_policies(
        self,
        policy_request: RuntimePolicyRequest,
        result: Any,
    ) -> None:
        """Apply all after-run RuntimePolicy instances (non-blocking)."""
        if isinstance(self._safety_policy, RuntimePolicy):
            await self._safety_policy.after_run(policy_request, result)

    # ------------------------------------------------------------------
    # Main execution methods (ExecutableAgent protocol)
    # ------------------------------------------------------------------

    async def ainvoke(self, request: AgentRunRequest) -> AgentRunResult:
        """Execute the agent with the given run request, applying all policies."""
        await self.ensure_loaded()

        # Convert AgentRunRequest to legacy input format for graph.
        input_data = request.inputs
        config = request.settings.get("config") if request.settings else None

        # Save original messages for memory extraction.
        original_messages = []
        if isinstance(input_data, dict) and "messages" in input_data:
            original_messages = list(input_data["messages"])

        # Build policy request.
        policy_request = RuntimePolicyRequest(
            agent=self,
            inputs=input_data,
            state=request.settings or {},
        )

        # Apply before-run policies.
        await self._apply_before_run_policies(policy_request)

        # Inject memory context.
        input_data, memories, user_id = await self._inject_memory_into_input(input_data, config)

        # Set trusted context.
        trusted_ctx = self._get_trusted_context(config)
        token = _trusted_context_var.set(trusted_ctx)

        try:
            # Execute via the pre-built executable agent.
            if self._executable_agent is not None:
                raw_result = await self._executable_agent.ainvoke(
                    AgentRunRequest(inputs=input_data, settings=request.settings)
                )
            else:
                raise RuntimeError("No executable agent available for invocation")
        finally:
            _trusted_context_var.reset(token)

        result = raw_result.output if isinstance(raw_result, AgentRunResult) else raw_result

        # Tag output with memory recall.
        result = self._tag_output_with_recalled_memories(result, memories)

        # Save memories from output.
        if memories and user_id:
            await self._memory_policy.after_run(
                output=result,
                original_messages=original_messages,
                memories=memories,
                user_id=user_id,
                config=config,
            )

        # Apply after-run policies.
        await self._apply_after_run_policies(policy_request, result)

        metadata = raw_result.metadata if isinstance(raw_result, AgentRunResult) else {}
        return AgentRunResult(output=result, metadata=metadata)

    async def astream(self, request: AgentRunRequest) -> AsyncIterator[AgentChunk]:
        """Stream agent execution with memory and policy support."""
        await self.ensure_loaded()

        input_data = request.inputs
        config = request.settings.get("config") if request.settings else None

        # Save original messages for memory extraction.
        original_messages = []
        if isinstance(input_data, dict) and "messages" in input_data:
            original_messages = list(input_data["messages"])

        # Inject memory context.
        input_data, memories, user_id = await self._inject_memory_into_input(input_data, config)

        # Emit memory recall event.
        recall_event = self._build_memory_recall_event(memories)
        if recall_event is not None:
            yield AgentChunk(delta="", metadata={"event": recall_event})

        # Set trusted context.
        trusted_ctx = self._get_trusted_context(config)
        token = _trusted_context_var.set(trusted_ctx)

        collected_output = None
        try:
            if self._executable_agent is not None:
                enriched_request = AgentRunRequest(inputs=input_data, settings=request.settings)
                async for chunk in self._executable_agent.astream(enriched_request):
                    chunk = self._tag_output_with_recalled_memories(chunk, memories)
                    collected_output = chunk
                    yield AgentChunk(delta=str(chunk), metadata={})
            else:
                raise RuntimeError("No executable agent available for streaming")
        finally:
            _trusted_context_var.reset(token)

        # Save memories from the last chunk.
        if collected_output is not None and memories and user_id:
            try:
                await self._memory_policy.after_run(
                    output=collected_output,
                    original_messages=original_messages,
                    memories=memories,
                    user_id=user_id,
                    config=config,
                )
            except Exception as e:
                logger.warning("[ComposedAgent] Memory save after stream failed: %s", e)

    async def astream_events(self, request: AgentRunRequest) -> AsyncIterator[AgentEvent]:
        """Stream agent events with memory and policy support."""
        await self.ensure_loaded()

        input_data = request.inputs
        config = request.settings.get("config") if request.settings else None

        # Save original messages for memory extraction.
        original_messages = []
        if isinstance(input_data, dict) and "messages" in input_data:
            original_messages = list(input_data["messages"])

        # Inject memory context.
        input_data, memories, user_id = await self._inject_memory_into_input(input_data, config)

        # Collect AI response messages from events for memory extraction.
        response_messages: list = []

        # Set trusted context.
        trusted_ctx = self._get_trusted_context(config)
        token = _trusted_context_var.set(trusted_ctx)

        try:
            if self._executable_agent is not None:
                enriched_request = AgentRunRequest(inputs=input_data, settings=request.settings)
                async for event in self._executable_agent.astream_events(enriched_request):
                    if isinstance(event, AgentEvent):
                        event_name = event.name
                        payload = event.payload
                    elif isinstance(event, Mapping):
                        event_name = str(event.get("event", "unknown"))
                        payload = event
                    else:
                        event_name = "unknown"
                        payload = {"event": event}

                    if event_name == "on_chat_model_end":
                        output = payload.get("data", {}).get("output")
                        if output is not None and hasattr(output, "content"):
                            response_messages.append(output)
                    yield AgentEvent(name=event_name, payload=payload)
            else:
                raise RuntimeError("No executable agent available for events streaming")
        finally:
            _trusted_context_var.reset(token)

        # Save memories after streaming completes.
        if memories and user_id:
            try:
                await self._memory_policy.after_run(
                    output={"messages": response_messages},
                    original_messages=original_messages,
                    memories=memories,
                    user_id=user_id,
                    config=config,
                )
            except Exception as e:
                logger.warning("[ComposedAgent] Memory save after stream_events failed: %s", e)
