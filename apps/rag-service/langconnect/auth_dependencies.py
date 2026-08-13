"""Permission check dependencies for RAG routes.

Use these to protect collection and connector endpoints with new permission system.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from langconnect.auth import AuthenticatedUser, require_user
from langconnect.services.permission_service import get_permission_service


async def require_collection_access(
    collection_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    required_permission: str = "read",
) -> AuthenticatedUser:
    """Dependency to check if user can access a collection.

    Usage in route:
        @router.get("/collections/{collection_id}")
        async def get_collection(
            collection_id: UUID,
            user: Annotated[AuthenticatedUser, Depends(require_collection_access)]
        ):
            ...

    Args:
        collection_id: Collection UUID from path parameter
        user: Authenticated user
        required_permission: Minimum permission level required

    Returns:
        AuthenticatedUser if access is granted

    Raises:
        HTTPException 403 if access denied
    """
    perm_service = get_permission_service()

    access = await perm_service.check_collection_access(
        user_id=user.user_id,
        collection_id=str(collection_id),
        required_permission=required_permission,
    )

    if not access["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to collection {collection_id}. Required permission: {required_permission}",
        )

    return user


async def require_connector_access(
    connector_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(require_user)],
    required_permission: str = "read",
) -> AuthenticatedUser:
    """Dependency to check if user can access a connector.

    Usage in route:
        @router.get("/connectors/{connector_id}")
        async def get_connector(
            connector_id: UUID,
            user: Annotated[AuthenticatedUser, Depends(require_connector_access)]
        ):
            ...

    Args:
        connector_id: Connector UUID from path parameter
        user: Authenticated user
        required_permission: Minimum permission level required

    Returns:
        AuthenticatedUser if access is granted

    Raises:
        HTTPException 403 if access denied
    """
    perm_service = get_permission_service()

    access = await perm_service.check_connector_access(
        user_id=user.user_id,
        connector_id=str(connector_id),
        required_permission=required_permission,
    )

    if not access["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to connector {connector_id}. Required permission: {required_permission}",
        )

    return user


def require_collection_permission(permission_level: str):
    """Factory to create collection permission dependency with specific level.

    Usage:
        @router.delete("/collections/{collection_id}")
        async def delete_collection(
            collection_id: UUID,
            user: Annotated[AuthenticatedUser, Depends(require_collection_permission("owner"))]
        ):
            ...
    """

    async def _check(
        collection_id: UUID,
        user: Annotated[AuthenticatedUser, Depends(require_user)],
    ) -> AuthenticatedUser:
        return await require_collection_access(collection_id, user, permission_level)

    return _check


def require_connector_permission(permission_level: str):
    """Factory to create connector permission dependency with specific level.

    Usage:
        @router.put("/connectors/{connector_id}")
        async def update_connector(
            connector_id: UUID,
            user: Annotated[AuthenticatedUser, Depends(require_connector_permission("write"))]
        ):
            ...
    """

    async def _check(
        connector_id: UUID,
        user: Annotated[AuthenticatedUser, Depends(require_user)],
    ) -> AuthenticatedUser:
        return await require_connector_access(connector_id, user, permission_level)

    return _check
