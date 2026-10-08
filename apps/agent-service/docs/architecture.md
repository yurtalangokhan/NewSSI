# Agent service architecture

Agent service separates HTTP delivery from runtime agent construction. New
agent behavior must extend composition components, graph strategies, recipes, or
tools-service tools instead of adding isolated agent modules.

## Request flow

Agent requests enter through FastAPI routes, move through the service
layer, and create executable agents through the composition package.

```text
api/routes -> service -> AgentFactory -> AgentComposer -> ComposedAgent
```

`ComposedAgent` owns runtime resources after `load()`. It exposes invoke,
stream, event stream, state, and history operations to the service layer.

## Dynamic agents

Dynamic agent definitions are persisted through
`src/repository/agent_definition_repository.py` and stored with the database
models in `src/core/db/models/agent_definition.py`. Definitions store stable
component keys, graph schema names, tool selections, and runtime policy config.
They don't store Python class paths or hardcoded model names.

## Built-in agents

Built-in agents are recipes in
`src/agent_composition/application/recipes.py`. Recipes must stay
model-agnostic unless a caller explicitly supplies a model override. Runtime
provider and default-model resolution choose the actual model.

## Chat runs runtime

Chat agent runs survive client disconnects. Each accepted send becomes a chat
run that a per-process `ChatRunSupervisor` (`src/service/chat_runs/`) executes
in an asyncio task it owns; HTTP handlers only subscribe through a
`RunEventReader`. One active run is allowed per thread, enforced by a
lease-aware Redis registry (reject policy: `409 chat_run.active`), and every
frame is appended to a Redis Stream so any authorized tab can replay or re-attach.

The layering stays framework- and I/O-free below the route:

```text
api/routes/chat_route.py -> service/chat_runs/service.py -> supervisor/reader/reaper
                                                     |
                                     ports.py (RunRegistry, RunEventLog)
                                                     |
                       infrastructure/runtime/chat_runs/* (Redis adapters)
```

Run states are `running -> completed | failed | cancelled | interrupted`.
Finalization is idempotent and fenced: terminal status is committed by
compare-and-set in the registry before the `run_end` frame is appended, and the
event log rejects any write at or below its last sequence, so a worker that
lost its lease (or a reaper on another instance) can never produce a second
terminal frame. A lease-aware `OrphanRunReaper` closes runs whose worker died
as `interrupted`; that work is never re-executed. Stop is cooperative first
(`cancel_all_for_thread`), then a hard cancel after the grace period, and a
disconnect never cancels a run. Sessions are titled server-side on completion
through a run-completion hook guarded by a Redis naming lock, so titling no
longer depends on the requesting tab staying open.

### Capacity and Redis usage

Chat runs use two Redis pools of their own, derived from the shared client's
connection settings, and never the shared idempotency pool. The writer pool
(50 connections, waits up to 2 s) carries token writes, leases and the reaper.
The reader pool (100 connections, waits up to 10 s) carries SSE viewers. Both
wait for a free connection instead of failing, so a burst of viewers can't fail
token writes, lease renewals or idempotent POSTs.

- **Readers poll, they don't block.** A viewer reads the stream every 50 ms
  while events arrive and backs off to 500 ms while the run is quiet. A
  blocking `XREAD` would pin one connection per open stream; redis-py fails at
  once when a pool is exhausted, which took runs down at about 100 viewers per
  replica.
- **Commands are pipelined across runs.** Token `XADD`s and viewer `XRANGE`s
  issued concurrently by many runs go out together in the next pipeline, so a
  replica's Redis cost doesn't grow with one round trip per token.

Measured on one process against a local Redis
(`tests/integration/test_chat_runs_under_load.py`, 300 tokens per run at
50 tokens/s, every viewer dropping and re-attaching with a full replay
mid-run): 200 runs with 400 viewers finish in 7.9 s against a 6 s nominal run,
and 400 runs with 800 viewers in 10.7 s. Heartbeat lag stays under 20 ms and
Redis connections stay at about 150.

Health signals are exported on `/metrics`:

| Metric | Meaning |
|---|---|
| `chat_runs_active` | Runs this process is executing. |
| `chat_run_event_streams_open` | Open SSE subscriptions. |
| `chat_runs_finished_total{status,reason}` | Recorded end states; `reason` is a platform reason or `agent_error`. |
| `chat_run_heartbeat_lag_seconds` | How late lease heartbeats woke up. Every run on a process shares one event loop, so blocking code there delays every lease; a lag near `CHAT_RUN_LEASE_TTL_SECONDS` means other instances are about to reap all of them. A stall of one heartbeat interval or more is also logged as `chat_run.event_loop_stall`. |

## Tools boundary

Tools-service owns reusable tool implementations. Agent service selects tools,
passes trusted invocation context, and calls tools through
`ToolsServiceToolGateway`. Do not add new generic tools under
`src/agents/`.

Knowledge retrieval follows this boundary: agent service maps `rag_config` to
the tools-service `database_search` and `graph_search` tools, and tools-service
calls rag-service retrieval endpoints.

Their evidence (the chunks or subgraph the model received) arrives as MCP
structured content. `KnowledgeEvidenceArtifactPolicy` stores it in the
thread-scoped `knowledge_evidence` table and puts only the row id on the
ToolMessage artifact, because the checkpoint rewrites the whole message list on
every step. `src/service/knowledge_evidence/` owns recording, hydration of
`knowledge_retrieval` packets for the live stream and for history, and the
evidence of flow retrieval nodes. Rows are deleted with their thread.
