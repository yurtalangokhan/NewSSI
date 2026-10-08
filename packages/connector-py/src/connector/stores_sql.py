"""Durable stores on SQLAlchemy (async): connections, jobs, sync state, schedules.

Works with any async SQLAlchemy URL, e.g. ``postgresql+asyncpg://...`` in
production or ``sqlite+aiosqlite:///connector.db`` for a single node. Requires
the ``sql`` extra (``pip install connector-py[sql]``) plus the driver.

Layout: each table keeps the full pydantic model as JSON text in ``payload`` and
lifts only the columns that queries filter or sort on. Timestamps used in
comparisons are stored as **epoch milliseconds** (integers) so that equality in
the scheduler's compare-and-set behaves identically on SQLite and PostgreSQL.

Secrets: pass a :class:`Cipher` and the ``source_config`` / ``destination_config``
of every connection are encrypted at rest as a whole, so no connector-specific
knowledge is needed to keep credentials out of the database in clear text.
"""

from __future__ import annotations

import builtins
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from .errors import ConnectorError, JobTakenOverError, MissingExtraError
from .extras import require_extra
from .models import Connection, Job, JobStatus, ScheduleEntry, SyncState, utcnow

try:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
except ImportError as exc:  # pragma: no cover - depends on extras
    raise MissingExtraError("SQL stores", "sql") from exc

_ENC_KEY = "__encrypted__"
_TERMINAL = [JobStatus.SUCCEEDED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]


def _ms(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(round(value.timestamp() * 1000))


class Cipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, token: str) -> str: ...


class FernetCipher:
    """Symmetric encryption with ``cryptography.fernet`` (``pip install connector-py[encryption]``).

    ``key`` is a urlsafe base64 32-byte key, e.g. ``Fernet.generate_key()``.
    """

    def __init__(self, key: str | bytes) -> None:
        fernet = require_extra("cryptography.fernet", extra="encryption", feature="FernetCipher")
        self._fernet = fernet.Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()


class SqlStores:
    """Creates the tables and hands out the four stores sharing one engine."""

    def __init__(
        self,
        engine: AsyncEngine | str,
        *,
        cipher: Cipher | None = None,
        table_prefix: str = "connector_",
        schema: str | None = None,
    ) -> None:
        self.engine: AsyncEngine = (
            create_async_engine(engine) if isinstance(engine, str) else engine
        )
        self._owns_engine = isinstance(engine, str)
        self.metadata = sa.MetaData(schema=schema)
        p = table_prefix
        self.t_connections = sa.Table(
            f"{p}connections",
            self.metadata,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("source_name", sa.String(100), nullable=False),
            sa.Column("destination_name", sa.String(100), nullable=False),
            sa.Column("payload", sa.Text, nullable=False),
            sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
        )
        self.t_jobs = sa.Table(
            f"{p}jobs",
            self.metadata,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("connection_id", sa.String(64), nullable=False, index=True),
            sa.Column("status", sa.String(20), nullable=False, index=True),
            sa.Column("created_at_ms", sa.BigInteger, nullable=False, index=True),
            sa.Column("heartbeat_at_ms", sa.BigInteger),
            sa.Column("payload", sa.Text, nullable=False),
        )
        self.t_states = sa.Table(
            f"{p}states",
            self.metadata,
            sa.Column("connection_id", sa.String(64), primary_key=True),
            sa.Column("payload", sa.Text, nullable=False),
            sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
        )
        self.t_schedules = sa.Table(
            f"{p}schedules",
            self.metadata,
            sa.Column("connection_id", sa.String(64), primary_key=True),
            sa.Column("next_run_at_ms", sa.BigInteger, index=True),
            sa.Column("enabled", sa.Boolean, nullable=False, default=True),
            sa.Column("payload", sa.Text, nullable=False),
        )
        self.connections = SqlConnectionStore(self, cipher)
        self.jobs = SqlJobStore(self)
        self.states = SqlStateStore(self)
        self.schedules = SqlScheduleStore(self)

    async def create_tables(self) -> None:
        """Idempotent. Services that manage schema with Alembic can skip this and
        create the same tables in a migration instead."""
        async with self.engine.begin() as conn:
            await conn.run_sync(self.metadata.create_all)

    async def close(self) -> None:
        if self._owns_engine:
            await self.engine.dispose()

    async def _upsert(self, table: sa.Table, key: str, row: dict[str, Any]) -> None:
        """Portable upsert: update, and insert when nothing was updated."""
        async with self.engine.begin() as conn:
            values = {k: v for k, v in row.items() if k != key}
            result = await conn.execute(
                sa.update(table).where(table.c[key] == row[key]).values(**values)
            )
            if result.rowcount == 0:
                await conn.execute(sa.insert(table).values(**row))


class SqlStateStore:
    def __init__(self, stores: SqlStores) -> None:
        self._s = stores

    async def load(self, connection_id: str) -> SyncState:
        t = self._s.t_states
        async with self._s.engine.connect() as conn:
            row = (
                await conn.execute(sa.select(t.c.payload).where(t.c.connection_id == connection_id))
            ).first()
        return SyncState.model_validate_json(row[0]) if row else SyncState()

    async def save(self, connection_id: str, state: SyncState) -> None:
        await self._s._upsert(
            self._s.t_states,
            "connection_id",
            {
                "connection_id": connection_id,
                "payload": state.model_dump_json(),
                "updated_at_ms": _ms(utcnow()),
            },
        )

    async def reset(self, connection_id: str) -> None:
        t = self._s.t_states
        async with self._s.engine.begin() as conn:
            await conn.execute(sa.delete(t).where(t.c.connection_id == connection_id))


class SqlJobStore:
    def __init__(self, stores: SqlStores) -> None:
        self._s = stores

    @staticmethod
    def _row(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "connection_id": job.connection_id,
            "status": job.status.value,
            "created_at_ms": _ms(job.created_at),
            "heartbeat_at_ms": _ms(job.heartbeat_at),
            "payload": job.model_dump_json(),
        }

    async def create(self, job: Job) -> Job:
        await self._s._upsert(self._s.t_jobs, "id", self._row(job))
        return job

    async def create_exclusive(self, job: Job) -> Job | None:
        """Insert ``job`` unless its connection has another non-terminal job.

        One ``INSERT ... SELECT ... WHERE NOT EXISTS`` statement. That is atomic
        where writers are serialised (SQLite); under ``READ COMMITTED`` two
        replicas can still both pass. A partial unique index on
        ``connection_id`` for non-terminal statuses makes it strict there: the
        loser's ``IntegrityError`` is reported as "not created". The store does
        not declare that index itself (it would forbid ``allow_concurrent_jobs``);
        a host that runs several replicas adds it.

        Any other ``IntegrityError`` is raised: it does not mean the connection
        is being synced.
        """
        t = self._s.t_jobs
        row = self._row(job)
        live = sa.select(t.c.id).where(
            t.c.connection_id == job.connection_id, t.c.status.not_in(_TERMINAL)
        )
        values = sa.select(
            *(sa.literal(value, type_=t.c[name].type) for name, value in row.items())
        ).where(~live.exists())
        try:
            async with self._s.engine.begin() as conn:
                result = await conn.execute(sa.insert(t).from_select(list(row), values))
        except sa.exc.IntegrityError:
            # Lost the race only if the winner's job is there to be seen.
            if await self.list_active(job.connection_id):
                return None
            raise
        return job if result.rowcount else None

    async def update(self, job: Job) -> Job:
        if job.is_terminal:
            await self._s._upsert(self._s.t_jobs, "id", self._row(job))
            return job
        # A live status is written only over a live one: a job another worker ended
        # (a stale-job takeover) stays ended, and this worker learns about it.
        t = self._s.t_jobs
        row = self._row(job)
        values = {k: v for k, v in row.items() if k != "id"}
        async with self._s.engine.begin() as conn:
            result = await conn.execute(
                sa.update(t).where(t.c.id == job.id, t.c.status.not_in(_TERMINAL)).values(**values)
            )
            if result.rowcount == 0:
                exists = (await conn.execute(sa.select(t.c.id).where(t.c.id == job.id))).first()
                if exists is not None:
                    raise JobTakenOverError(job.id)
                await conn.execute(sa.insert(t).values(**row))
        return job

    async def get(self, job_id: str) -> Job | None:
        t = self._s.t_jobs
        async with self._s.engine.connect() as conn:
            row = (await conn.execute(sa.select(t.c.payload).where(t.c.id == job_id))).first()
        return Job.model_validate_json(row[0]) if row else None

    async def list(self, connection_id: str | None = None, limit: int = 50) -> list[Job]:
        t = self._s.t_jobs
        query = sa.select(t.c.payload).order_by(t.c.created_at_ms.desc()).limit(limit)
        if connection_id is not None:
            query = query.where(t.c.connection_id == connection_id)
        async with self._s.engine.connect() as conn:
            rows = (await conn.execute(query)).all()
        return [Job.model_validate_json(r[0]) for r in rows]

    async def list_active(self, connection_id: str | None = None) -> builtins.list[Job]:
        t = self._s.t_jobs
        query = sa.select(t.c.payload).where(t.c.status.not_in(_TERMINAL))
        if connection_id is not None:
            query = query.where(t.c.connection_id == connection_id)
        async with self._s.engine.connect() as conn:
            rows = (await conn.execute(query)).all()
        return [Job.model_validate_json(r[0]) for r in rows]

    async def purge(self, older_than: datetime) -> int:
        """Delete finished jobs created before ``older_than``. Returns rows removed."""
        t = self._s.t_jobs
        async with self._s.engine.begin() as conn:
            result = await conn.execute(
                sa.delete(t).where(t.c.status.in_(_TERMINAL), t.c.created_at_ms < _ms(older_than))
            )
        return int(result.rowcount or 0)


class SqlConnectionStore:
    def __init__(self, stores: SqlStores, cipher: Cipher | None = None) -> None:
        self._s = stores
        self._cipher = cipher

    def _dump(self, connection: Connection) -> str:
        data = connection.model_dump(mode="json")
        if self._cipher is not None:
            for key in ("source_config", "destination_config"):
                data[key] = {_ENC_KEY: self._cipher.encrypt(json.dumps(data[key]))}
        return json.dumps(data)

    def _load(self, payload: str) -> Connection:
        data = json.loads(payload)
        for key in ("source_config", "destination_config"):
            value = data.get(key)
            if isinstance(value, dict) and _ENC_KEY in value:
                if self._cipher is None:
                    raise ConnectorError("connection configs are encrypted but no cipher was given")
                data[key] = json.loads(self._cipher.decrypt(value[_ENC_KEY]))
        return Connection.model_validate(data)

    def _row(self, connection: Connection) -> dict[str, Any]:
        return {
            "id": connection.id,
            "name": connection.name,
            "source_name": connection.source_name,
            "destination_name": connection.destination_name,
            "payload": self._dump(connection),
            "updated_at_ms": _ms(utcnow()),
        }

    async def create(self, connection: Connection) -> Connection:
        await self._s._upsert(self._s.t_connections, "id", self._row(connection))
        return connection

    async def update(self, connection: Connection) -> Connection:
        await self._s._upsert(self._s.t_connections, "id", self._row(connection))
        return connection

    async def get(self, connection_id: str) -> Connection | None:
        t = self._s.t_connections
        async with self._s.engine.connect() as conn:
            row = (
                await conn.execute(sa.select(t.c.payload).where(t.c.id == connection_id))
            ).first()
        return self._load(row[0]) if row else None

    async def list(self) -> list[Connection]:
        t = self._s.t_connections
        async with self._s.engine.connect() as conn:
            rows = (await conn.execute(sa.select(t.c.payload).order_by(t.c.name))).all()
        return [self._load(r[0]) for r in rows]

    async def delete(self, connection_id: str) -> None:
        s = self._s
        async with s.engine.begin() as conn:
            await conn.execute(
                sa.delete(s.t_connections).where(s.t_connections.c.id == connection_id)
            )
            await conn.execute(
                sa.delete(s.t_schedules).where(s.t_schedules.c.connection_id == connection_id)
            )
            await conn.execute(
                sa.delete(s.t_states).where(s.t_states.c.connection_id == connection_id)
            )


class SqlScheduleStore:
    def __init__(self, stores: SqlStores) -> None:
        self._s = stores

    async def get(self, connection_id: str) -> ScheduleEntry | None:
        t = self._s.t_schedules
        async with self._s.engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.select(t.c.payload, t.c.next_run_at_ms).where(
                        t.c.connection_id == connection_id
                    )
                )
            ).first()
        return self._entry(row) if row else None

    @staticmethod
    def _entry(row: Any) -> ScheduleEntry:
        entry = ScheduleEntry.model_validate_json(row[0])
        # The column is the source of truth: claim() moves it without touching the payload.
        entry.next_run_at = (
            datetime.fromtimestamp(row[1] / 1000, tz=UTC) if row[1] is not None else None
        )
        return entry

    async def upsert(self, entry: ScheduleEntry) -> ScheduleEntry:
        await self._s._upsert(
            self._s.t_schedules,
            "connection_id",
            {
                "connection_id": entry.connection_id,
                "next_run_at_ms": _ms(entry.next_run_at),
                "enabled": entry.enabled,
                "payload": entry.model_dump_json(),
            },
        )
        return entry

    async def delete(self, connection_id: str) -> None:
        t = self._s.t_schedules
        async with self._s.engine.begin() as conn:
            await conn.execute(sa.delete(t).where(t.c.connection_id == connection_id))

    async def list(self) -> list[ScheduleEntry]:
        t = self._s.t_schedules
        async with self._s.engine.connect() as conn:
            rows = (await conn.execute(sa.select(t.c.payload, t.c.next_run_at_ms))).all()
        return [self._entry(r) for r in rows]

    async def list_due(self, now: datetime, limit: int = 100) -> builtins.list[ScheduleEntry]:
        t = self._s.t_schedules
        query = (
            sa.select(t.c.payload, t.c.next_run_at_ms)
            .where(t.c.enabled.is_(True), t.c.next_run_at_ms <= _ms(now))
            .order_by(t.c.next_run_at_ms)
            .limit(limit)
        )
        async with self._s.engine.connect() as conn:
            rows = (await conn.execute(query)).all()
        return [self._entry(r) for r in rows]

    async def claim(
        self, connection_id: str, expected_next_run_at: datetime | None, new_next_run_at: datetime
    ) -> bool:
        t = self._s.t_schedules
        expected = _ms(expected_next_run_at)
        condition = (
            t.c.next_run_at_ms.is_(None) if expected is None else t.c.next_run_at_ms == expected
        )
        async with self._s.engine.begin() as conn:
            result = await conn.execute(
                sa.update(t)
                .where(t.c.connection_id == connection_id, condition)
                .values(next_run_at_ms=_ms(new_next_run_at))
            )
        return result.rowcount == 1
