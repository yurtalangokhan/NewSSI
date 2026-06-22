from .auth_route import router as auth_router
from .user_route import router as user_router
from .settings_route import router as settings_router
from .api_keys_route import router as api_keys_router
from .roles_route import router as roles_router
from .permissions_route import router as permissions_router

api_router = [
    auth_router,
    user_router,
    settings_router,
    api_keys_router,
    roles_router,
    permissions_router,
]
