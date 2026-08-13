"""
Permission check dependency for agent routes.

Use this to protect agent endpoints with new permission system.
"""

from typing import Annotated

from fastapi import Depends, HTTPException

from api.dependencies import AuthenticatedUser, require_user
from service.permission_service import get_permission_service


async def require_agent_access(
    agent_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    required_permission: str = "execute",
) -> AuthenticatedUser:
    """
    Dependency to check if user can access an agent.

    Usage in route:
        @router.get("/agents/{agent_id}")
        async def get_agent(
            agent_id: str,
            user: Annotated[AuthenticatedUser, Depends(require_agent_access)]
        ):
            ...

    Args:
        agent_id: Agent ID from path parameter
        user: Authenticated user
        required_permission: Minimum permission level required

    Returns:
        AuthenticatedUser if access is granted

    Raises:
        HTTPException 403 if access denied
    """
    perm_service = get_permission_service()

    access = await perm_service.check_agent_access(
        user_id=user.user_id,
        agent_id=agent_id,
        required_permission=required_permission,
    )

    if not access["allowed"]:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to agent {agent_id}. Required permission: {required_permission}",
        )

    return user


def require_agent_permission(permission_level: str):
    """
    Factory to create permission dependency with specific level.

    Usage:
        @router.delete("/agents/{agent_id}")
        async def delete_agent(
            agent_id: str,
            user: Annotated[AuthenticatedUser, Depends(require_agent_permission("owner"))]
        ):
            ...
    """

    async def _check(
        agent_id: str,
        user: Annotated[AuthenticatedUser, Depends(require_user)],
    ) -> AuthenticatedUser:
        return await require_agent_access(agent_id, user, permission_level)

    return _check
