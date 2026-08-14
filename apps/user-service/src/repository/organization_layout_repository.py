"""Repository operations for shared organization canvas layouts."""

import uuid
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from src.core.database.models import (
    CompositeRoleModel,
    OrganizationLayoutModel,
    OrganizationModel,
    UserModel,
    UserOrganizationModel,
)
from src.core.exceptions import ConflictError, NotFoundError

from .base_repository import BaseRepository


class OrganizationLayoutRepository(BaseRepository):
    """Read and atomically upsert shared organization layout coordinates."""

    async def get_all_positions(self) -> list[dict[str, Any]]:
        """Return every saved coordinate in stable organization-ID order."""
        async with self._session() as session:
            result = await session.execute(
                select(OrganizationLayoutModel).order_by(OrganizationLayoutModel.organization_id)
            )
            return [self._to_dict(layout) for layout in result.scalars().all()]

    async def get_existing_organization_ids(
        self, organization_ids: set[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return which requested organizations exist before scope validation."""
        if not organization_ids:
            return set()
        async with self._session() as session:
            result = await session.execute(
                select(OrganizationModel.id).where(OrganizationModel.id.in_(organization_ids))
            )
            return set(result.scalars().all())

    async def get_writable_organization_ids(self, actor_id: uuid.UUID) -> list[uuid.UUID]:
        """Derive all writable organizations with set-based database queries."""
        async with self._session() as session:
            actor_result = await session.execute(
                select(CompositeRoleModel.is_admin)
                .outerjoin(CompositeRoleModel, CompositeRoleModel.name == UserModel.role)
                .where(UserModel.id == actor_id)
            )
            actor = actor_result.one_or_none()
            if not actor:
                return []

            (is_admin,) = actor
            if is_admin:
                result = await session.execute(
                    select(OrganizationModel.id).order_by(OrganizationModel.id)
                )
                return list(result.scalars().all())

            managed_path = func.concat(
                "%/", cast(UserOrganizationModel.organization_id, String), "/%"
            )
            result = await session.execute(
                select(OrganizationModel.id)
                .join(
                    UserOrganizationModel,
                    or_(
                        OrganizationModel.id == UserOrganizationModel.organization_id,
                        OrganizationModel.path.like(managed_path),
                    ),
                )
                .where(
                    UserOrganizationModel.user_id == actor_id,
                    UserOrganizationModel.role_in_org == "unit_manager",
                    UserOrganizationModel.is_active,
                )
                .distinct()
                .order_by(OrganizationModel.id)
            )
            return list(result.scalars().all())

    async def bulk_upsert_positions(self, positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate requested organizations and upsert all positions atomically."""
        if not positions:
            return []

        organization_ids = {position["organization_id"] for position in positions}
        try:
            async with self._session() as session:
                existing_result = await session.execute(
                    select(OrganizationModel.id)
                    .where(OrganizationModel.id.in_(organization_ids))
                    .with_for_update()
                )
                existing_ids = set(existing_result.scalars().all())
                missing_ids = organization_ids - existing_ids
                if missing_ids:
                    missing_id = min(missing_ids, key=str)
                    raise NotFoundError(f"Organization {missing_id} not found")

                statement = insert(OrganizationLayoutModel).values(
                    [
                        {
                            "organization_id": position["organization_id"],
                            "position_x": position["x"],
                            "position_y": position["y"],
                        }
                        for position in positions
                    ]
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[OrganizationLayoutModel.organization_id],
                    set_={
                        "position_x": statement.excluded.position_x,
                        "position_y": statement.excluded.position_y,
                        "updated_at": func.now(),
                    },
                )
                await session.execute(statement)
                updated_result = await session.execute(
                    select(OrganizationLayoutModel)
                    .where(OrganizationLayoutModel.organization_id.in_(organization_ids))
                    .order_by(OrganizationLayoutModel.organization_id)
                )
                return [self._to_dict(layout) for layout in updated_result.scalars().all()]
        except IntegrityError as error:
            if self._is_foreign_key_violation(error):
                raise NotFoundError("Organization not found") from error
            raise ConflictError("Organization layout persistence conflict") from error

    @staticmethod
    def _is_foreign_key_violation(error: IntegrityError) -> bool:
        """Identify a deleted organization across supported database drivers."""
        original_error = error.orig
        error_code = (
            getattr(original_error, "sqlstate", None)
            or getattr(original_error, "pgcode", None)
            or getattr(original_error, "sqlite_errorname", None)
        )
        if error_code in {"23503", "SQLITE_CONSTRAINT_FOREIGNKEY"}:
            return True

        error_message = f"{original_error} {error}".lower()
        return "foreign key" in error_message or "foreignkey" in error_message

    @staticmethod
    def _to_dict(layout: OrganizationLayoutModel) -> dict[str, Any]:
        """Map a layout model to the public persistence representation."""
        return {
            "organization_id": layout.organization_id,
            "x": layout.position_x,
            "y": layout.position_y,
        }
