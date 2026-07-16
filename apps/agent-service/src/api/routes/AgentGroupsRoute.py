"""Agent access group routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import AuthenticatedUser, require_permission, require_user
from core.db.repositories.agent_group_repo import AgentGroupRepository
from models.agent_groups import AgentGroupUpsertRequest

router = APIRouter(
    prefix="/api/agent-groups",
    tags=["agent-groups"],
    dependencies=[Depends(require_user)],
)


def _repo() -> AgentGroupRepository:
    return AgentGroupRepository()


@router.get("")
async def list_agent_groups(
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:read"))],
) -> list[dict[str, Any]]:
    return await _repo().list_all()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_agent_group(
    body: AgentGroupUpsertRequest,
    user: Annotated[AuthenticatedUser, Depends(require_permission("agent:assign"))],
) -> dict[str, Any]:
    try:
        return await _repo().create(
            name=body.name.strip(),
            description=body.description.strip(),
            user_ids=body.user_ids,
            persona_ids=body.persona_ids,
            created_by=user.user_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{group_id}")
async def update_agent_group(
    group_id: int,
    body: AgentGroupUpsertRequest,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:assign"))],
) -> dict[str, Any]:
    try:
        group = await _repo().update(
            group_id,
            name=body.name.strip(),
            description=body.description.strip(),
            user_ids=body.user_ids,
            persona_ids=body.persona_ids,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not group:
        raise HTTPException(status_code=404, detail="Agent group not found")
    return group


@router.delete("/{group_id}")
async def delete_agent_group(
    group_id: int,
    _user: Annotated[AuthenticatedUser, Depends(require_permission("agent:assign"))],
) -> dict[str, bool]:
    deleted = await _repo().delete(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent group not found")
    return {"success": True}
