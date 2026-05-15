from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from core.database.engine import close_db_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_db_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="User Service",
        description="User Management Microservice — Auth, Users, Roles, Permissions",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.routes import api_keys_router, auth_router, roles_router, settings_router, user_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(user_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(api_keys_router, prefix="/api")
    app.include_router(roles_router, prefix="/api")

    from api.routes.health import router as health_router
    app.include_router(health_router, prefix="/health")

    return app


app = create_app()
