"""Repository for SMTP mail configurations."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, update

from core.db.models.mail_config import MailConfigModel
from core.db.models.persona import PersonaModel
from core.db.models.user_mail_credential import UserMailCredentialModel
from core.db.repositories.base import BaseRepository


def _mail_config_id_ref(column: Any) -> Any:
    """``column -> 'send_email' ->> 'mail_config_id'`` as a text expression.

    Uses the ``->`` / ``->>`` operators instead of the ORM subscript accessor
    (``column["send_email"]["mail_config_id"]``). The models type these columns
    as ``JSONB``, so the subscript form renders a PostgreSQL ``[]`` subscript,
    which only ``jsonb`` supports — against a database where the column is still
    ``json`` it raises "cannot subscript type json". ``->`` / ``->>`` behave
    identically on ``json`` and ``jsonb``, so this works regardless of the
    column's on-disk type.
    """
    return column.op("->")("send_email").op("->>")("mail_config_id")


def _normalize_user_ids(user_ids: Iterable[Any] | None) -> list[str]:
    """Stringify, drop blanks, and de-duplicate while preserving order."""
    seen: list[str] = []
    for user_id in user_ids or []:
        if not user_id:
            continue
        candidate = str(user_id)
        if candidate not in seen:
            seen.append(candidate)
    return seen


def _search_clause(search: str | None) -> Any | None:
    """Case-insensitive match across the fields the admin list searches on."""
    if not search or not search.strip():
        return None
    term = f"%{search.strip()}%"
    return or_(
        MailConfigModel.name.ilike(term),
        MailConfigModel.from_email.ilike(term),
        MailConfigModel.host.ilike(term),
        MailConfigModel.username.ilike(term),
        MailConfigModel.from_name.ilike(term),
    )


class MailConfigRepository(BaseRepository):
    """CRUD operations for the ``mail_config`` table.

    Two access patterns coexist. Admin-managed configs are shared: the
    ``*_active`` readers and the id-addressed writers see every active row, and
    a user binds their own SMTP credentials to one (see
    ``UserMailCredentialModel``). Owner-scoped callers instead pass a
    ``user_ids`` candidate list (produced by
    ``AuthService.resolve_known_user_ids`` at the service edge) and the query is
    filtered on ``user_id IN (...)``; an empty candidate list short-circuits to
    an empty result, so an owner-scoped call never widens into a cross-tenant
    query.
    """

    @staticmethod
    def parse_id(config_id: str) -> UUID | None:
        try:
            return UUID(config_id)
        except ValueError:
            return None

    # Kept as an alias: callers written against the private name still work.
    _parse_id = parse_id

    @staticmethod
    def _to_dict(row: MailConfigModel) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "user_id": row.user_id,
            "name": row.name,
            "host": row.host,
            "port": row.port,
            "username": row.username,
            "password_encrypted": row.password_encrypted,
            "from_email": row.from_email,
            "from_name": row.from_name,
            "security": row.security,
            "is_active": row.is_active,
            "last_tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
            "last_test_status": row.last_test_status,
            "last_test_error": row.last_test_error,
            "time_created": row.time_created.isoformat() if row.time_created else None,
            "time_updated": row.time_updated.isoformat() if row.time_updated else None,
        }

    async def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.execute(
                select(MailConfigModel)
                .where(
                    MailConfigModel.user_id == user_id,
                    MailConfigModel.is_active.is_(True),
                )
                .order_by(MailConfigModel.name)
            )
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def list_active(
        self,
        search: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        async with self._session() as session:
            query = select(MailConfigModel).where(MailConfigModel.is_active.is_(True))
            clause = _search_clause(search)
            if clause is not None:
                query = query.where(clause)
            query = query.order_by(MailConfigModel.name, MailConfigModel.id)
            if page is not None and page_size is not None:
                query = query.offset(max(0, (page - 1) * page_size)).limit(page_size)
            result = await session.execute(query)
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def count_active(self, search: str | None = None) -> int:
        async with self._session() as session:
            query = select(func.count(MailConfigModel.id)).where(
                MailConfigModel.is_active.is_(True)
            )
            clause = _search_clause(search)
            if clause is not None:
                query = query.where(clause)
            result = await session.execute(query)
            return int(result.scalar() or 0)

    async def list_by_user_ids(
        self,
        user_ids: Iterable[Any] | None,
        search: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        owners = _normalize_user_ids(user_ids)
        if not owners:
            return []
        async with self._session() as session:
            query = select(MailConfigModel).where(
                MailConfigModel.user_id.in_(owners),
                MailConfigModel.is_active.is_(True),
            )
            clause = _search_clause(search)
            if clause is not None:
                query = query.where(clause)
            query = query.order_by(MailConfigModel.name)
            if page is not None and page_size is not None:
                query = query.offset(max(0, (page - 1) * page_size)).limit(page_size)

            result = await session.execute(query)
            rows = result.scalars().all()
        return [self._to_dict(row) for row in rows]

    async def count_by_user_ids(
        self,
        user_ids: Iterable[Any] | None,
        search: str | None = None,
    ) -> int:
        owners = _normalize_user_ids(user_ids)
        if not owners:
            return 0
        async with self._session() as session:
            query = select(func.count(MailConfigModel.id)).where(
                MailConfigModel.user_id.in_(owners),
                MailConfigModel.is_active.is_(True),
            )
            clause = _search_clause(search)
            if clause is not None:
                query = query.where(clause)
            result = await session.execute(query)
            return int(result.scalar() or 0)

    async def get_active_by_id(self, config_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(config_id)

    async def get_by_id(
        self,
        config_id: str,
        user_ids: Iterable[Any] | None = None,
    ) -> dict[str, Any] | None:
        parsed_id = self.parse_id(config_id)
        if not parsed_id:
            return None
        owners = _normalize_user_ids(user_ids)
        if user_ids is not None and not owners:
            return None
        async with self._session() as session:
            query = select(MailConfigModel).where(
                MailConfigModel.id == parsed_id,
                MailConfigModel.is_active.is_(True),
            )
            if owners:
                query = query.where(MailConfigModel.user_id.in_(owners))
            result = await session.execute(query)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def create(self, **values: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._session() as session:
            row = MailConfigModel(
                **values,
                is_active=True,
                time_created=now,
                time_updated=now,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return self._to_dict(row)

    async def update(
        self,
        config_id: str,
        *,
        user_ids: Iterable[Any] | None = None,
        **updates: Any,
    ) -> dict[str, Any] | None:
        parsed_id = self.parse_id(config_id)
        if not parsed_id:
            return None
        owners = _normalize_user_ids(user_ids)
        if user_ids is not None and not owners:
            return None
        cleaned = {key: value for key, value in updates.items() if value is not None}
        if not cleaned:
            return await self.get_by_id(config_id, user_ids)
        cleaned["time_updated"] = datetime.now(UTC)
        async with self._session() as session:
            statement = (
                update(MailConfigModel)
                .where(
                    MailConfigModel.id == parsed_id,
                    MailConfigModel.is_active.is_(True),
                )
                .values(**cleaned)
                .returning(MailConfigModel)
            )
            if owners:
                statement = statement.where(MailConfigModel.user_id.in_(owners))
            result = await session.execute(statement)
            row = result.scalar_one_or_none()
        return self._to_dict(row) if row else None

    async def deactivate(
        self,
        config_id: str,
        user_ids: Iterable[Any] | None = None,
    ) -> bool:
        parsed_id = self.parse_id(config_id)
        if not parsed_id:
            return False
        owners = _normalize_user_ids(user_ids)
        if user_ids is not None and not owners:
            return False
        async with self._session() as session:
            statement = (
                update(MailConfigModel)
                .where(
                    MailConfigModel.id == parsed_id,
                    MailConfigModel.is_active.is_(True),
                )
                .values(is_active=False, time_updated=datetime.now(UTC))
            )
            if owners:
                statement = statement.where(MailConfigModel.user_id.in_(owners))
            result = await session.execute(statement)
            return result.rowcount > 0

    async def mark_tested(
        self,
        config_id: str,
        status: str = "success",
        error: str | None = None,
        user_ids: Iterable[Any] | None = None,
    ) -> dict[str, Any] | None:
        return await self.update(
            config_id,
            user_ids=user_ids,
            last_tested_at=datetime.now(UTC),
            last_test_status=status,
            last_test_error=error,
        )

    async def has_active_bindings(
        self,
        config_id: str,
        user_ids: Iterable[Any] | None = None,
    ) -> bool:
        parsed_id = self.parse_id(config_id)
        if not parsed_id:
            return False
        owners = _normalize_user_ids(user_ids)
        if user_ids is not None and not owners:
            return False
        async with self._session() as session:
            credential_query = (
                select(UserMailCredentialModel.id)
                .where(
                    UserMailCredentialModel.mail_config_id == parsed_id,
                    UserMailCredentialModel.is_active.is_(True),
                )
                .limit(1)
            )
            if owners:
                credential_query = credential_query.where(
                    UserMailCredentialModel.user_id.in_(owners)
                )
            credential_result = await session.execute(credential_query)
            if credential_result.scalar_one_or_none() is not None:
                return True

            persona_query = (
                select(PersonaModel.id)
                .where(_mail_config_id_ref(PersonaModel.mcp_tool_configs) == config_id)
                .limit(1)
            )
            if owners:
                persona_query = persona_query.where(PersonaModel.user_id.in_(owners))
            persona_result = await session.execute(persona_query)
            if persona_result.scalar_one_or_none() is not None:
                return True

            from core.db.models.agent_definition import AgentDefinitionModel

            definition_query = (
                select(AgentDefinitionModel.id)
                .join(PersonaModel, AgentDefinitionModel.persona_id == PersonaModel.id)
                .where(
                    AgentDefinitionModel.is_active.is_(True),
                    _mail_config_id_ref(AgentDefinitionModel.mcp_tool_configs) == config_id,
                )
                .limit(1)
            )
            if owners:
                definition_query = definition_query.where(PersonaModel.user_id.in_(owners))
            definition_result = await session.execute(definition_query)
            return definition_result.scalar_one_or_none() is not None
