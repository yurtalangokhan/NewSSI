# Agent Service Composition

This document describes how agents are constructed and run in the agent-service
after the `agent-service-composition` workstream (ASC-0 … ASC-7). It is the
authoritative reference for the final runtime. The older monolithic agent
modules were verified orphaned and removed in ASC-7.

## Canonical construction path

All agents — built-in and persisted dynamic definitions — are composed through
the `agent_composition` package:

1. `AgentFactory.create(definition, execution_context)` is the single
   application entrypoint for building a new executable agent. It validates the
   definition, asks `AgentComposer` for an unloaded runtime, awaits
   `ComposedAgent.load()`, and returns the loaded runtime.
2. `AgentComposer` applies builder semantics: it resolves lazy component
   providers (brain, perceptrons, tool gateway, graph schema, runtime
   policies), validates compatibility, and assembles an unloaded
   `ComposedAgent`. It never opens network, model, store, or graph resources.
3. `ComposedAgent` is the sole owner of acquired runtime resources. Its
   idempotent `load()` / `close()` acquire and release them; it exposes
   `ainvoke`, `astream`, `astream_events`, `aget_state`, `aupdate_state`, and
   `aget_state_history`.

These classes live in:

- `src/agent_composition/application/compose_agent.py` — `AgentFactory`, `AgentComposer`
- `src/agent_composition/runtime/composed_agent.py` — `ComposedAgent`
- `src/agent_composition/domain/ports.py` — `Brain`, `Perceptron`, `ToolGateway`, `GraphSchemaStrategy`, `RuntimePolicy`, `ExecutableAgent`
- `src/agent_composition/runtime/` — lifecycle, checkpoint, memory, safety, retry policies

## Component selection

Definitions store stable component keys, never Python class paths. Components
are resolved through:

- `src/agent_composition/domain/component_catalog.py` — `COMPONENT_CATALOG` and `get_component`
- `src/agent_composition/domain/definitions.py` — `AgentDefinition`, `BrainConfig`, `GraphSchemaConfig`, `PerceptronConfig`, `ToolSelection`, `RuntimePolicyConfig`

## Graph schemas

Each graph topology is a `GraphSchemaStrategy` registered in
`GraphSchemaStrategyRegistry` (`src/agents/graphs/strategies/registry.py`).
Strategies live in `src/agents/graphs/strategies/`: `zero_shot`, `react`,
`supervisor`, `pipeline`, `plan_execute`, `self_reflect`. `GraphBuilder`
(`src/agents/graphs/builder.py`) selects a strategy by key. Pipeline stage order
is deterministic, not prompt-driven.

## Tool gateway

Agent-service selects tools; it does not implement them. The `ToolGateway` port
is implemented by `ToolsServiceToolGateway`
(`src/agent_composition/adapters/tools_service_gateway.py`), which resolves
remote tool handles from tools-service. The trusted invocation context
(`src/agent_composition/domain/trusted_context.py`) keeps credentials and
internal binding references out of model-visible arguments.

## Built-in agents and Studio

Built-in agents are recipes over the same composer used by persisted dynamic
agents:

- `src/agent_composition/application/recipes.py` — `BUILTIN_RECIPES` maps
  `chatbot`, `configurable-mcp-agent`, `pipeline`, `supervisor` to flat
  definition configs. Recipes don't pin a model; runtime provider/default-model
  resolution chooses the model unless a caller supplies an explicit override.
  `get_builtin_recipe(agent_id)` resolves one.
- `src/agents/agents.py` — the backward-compatible static registry facade.
  `chatbot` and `configurable-mcp-agent` are served from the static registry;
  `pipeline` and `supervisor` (recipe-only) are composed via `AgentFactory`.
- `src/agents/studio_graphs.py` — LangGraph Studio entrypoints. Each is a
  callable that builds a compiled graph from a model-agnostic recipe via
  `GraphBuilder`. `langgraph.json` points Studio at `studio_graphs.py` (graphs:
  `chatbot`, `research-assistant`, `rag-assistant`,
  `graph-rag-assistant`).

## Removed legacy modules (ASC-7)

The following were verified orphaned (no production or test importer) and
deleted in ASC-7:

- `src/agents/research_assistant.py`, `rag_assistant.py`, `graph_rag_assistant.py`
- `src/agents/factory/` — reflection `AgentFactory` reading class paths from JSON
- `src/agents/registry/` — legacy `@agent` registry
- `src/agents/configs/` — JSON configs for the reflection factory
- `src/agents/managers/` — duplicate supervisor/pipeline managers
- `src/agents/runtime/` — orphaned `instance_manager` that selected managers by name

## Retained local tool modules (not yet moved to tools-service)

The following local tool modules are still used by the live graph strategies
and ingestion/data paths, so they were intentionally retained (verification-first
deletion rule: do not delete a module with live importers):

- `src/agents/document_tools.py` — used by `graphs/strategies/*`, `graphs/builder.py`, `chatbot.py`, `configurable_mcp_agent.py`, and their tests.
- `src/agents/mail_tooling.py` — used by `graphs/strategies/*`, `graphs/builder.py`, `configurable_mcp_agent.py`.
- `src/agents/tools.py` — Milvus/vector-store and embedding helpers used by `IngestService`, `data_controller`, `DatasourcesRoute`, `base/perceptron.py`, `knowledge/tool_selector.py`, and `core/db/repositories/datasource_repo.py`.

Moving these behind tools-service / RAG-service contracts remains future work.
ASC-2 laid the trusted-context foundation; the local implementations are still
the runtime path today.

## Package exports

`src/agents/__init__.py` re-exports only the backward-compatible facade
(`get_agent`, `load_agent`, `get_all_agent_info`, `DEFAULT_AGENT`,
`AgentGraph`, `AgentGraphLike`) plus the retained `base` / `perceptron` /
`storage` contracts. The deleted island packages are no longer re-exported.
