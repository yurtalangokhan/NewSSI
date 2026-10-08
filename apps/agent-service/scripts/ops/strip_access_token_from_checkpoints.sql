-- Defensive cleanup for spec T3: the user's access_token must never be
-- persisted in LangGraph checkpoint state.
--
-- Investigation (2026-09-14, langgraph-checkpoint-postgres as pinned in
-- this service's lock file): AsyncPostgresSaver.aput() explicitly narrows
-- the persisted `configurable` to {thread_id, checkpoint_ns, checkpoint_id}
-- before storing it (see checkpoint/postgres/aio.py), so the
-- `access_token` key that agents/graphs/flow_builder.py and
-- service/AgentHelpers.py used to place into `configurable` does NOT
-- appear to round-trip through the `checkpoints.configurable` path that
-- feeds /threads/{id}/state's `parent_config` field in the pinned version.
-- The `checkpoints.metadata` JSONB column is a different, LangGraph-
-- Pregel-constructed value (source/step/parents/run_id) that also does
-- not appear to echo `configurable` in this version.
--
-- This script is kept anyway, as a zero-risk, idempotent defensive check:
-- it matches nothing (0 rows) if the above holds for every historical row,
-- and safely removes the key if a different code path, an earlier
-- dependency version, or a scenario this investigation did not cover
-- placed it there. It does NOT touch checkpoint_writes.blob (BYTEA,
-- serialized channel writes -- flow_builder.py's nodes never returned
-- access_token as part of their output state, and rewriting a
-- msgpack/pickle blob in place from SQL is unsafe to attempt blindly).
--
-- Run manually against the agent-service checkpoint database; not wired
-- into Alembic, since `checkpoints`/`checkpoint_writes` are managed by
-- AsyncPostgresSaver.setup(), not this service's own migrations.
--
-- Safe to run repeatedly (idempotent) and safe to run with zero effect.

BEGIN;

-- Report what would change before changing it.
SELECT thread_id, checkpoint_id
  FROM checkpoints
 WHERE metadata ? 'access_token';

UPDATE checkpoints
   SET metadata = metadata - 'access_token'
 WHERE metadata ? 'access_token';

COMMIT;
