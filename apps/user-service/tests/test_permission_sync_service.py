import importlib

from src.service import permission_sync_service
from src.service import permission_sync_service
from src.service.permission_sync_service import PermissionSyncService

coarse_roles_migration = importlib.import_module(
    "src.core.database.migrations.versions.0010_add_coarse_roles"
)


def test_collect_manifest_permissions_uses_user_service_manifest_location():
    service = PermissionSyncService()

    permissions, sources = service._collect_permissions()

    assert any(permission.name == "user:list" for permission in permissions)
    local_source = next(source for source in sources if source.service == "user-service")
    assert local_source.loaded is True
    assert local_source.path == "src/core/permissions/manifest.py"


def test_external_manifest_paths_tolerates_docker_image_layout(monkeypatch):
    monkeypatch.setattr(
        permission_sync_service,
        "__file__",
        "/app/src/service/permission_sync_service.py",
    )
    service = PermissionSyncService()

    paths = service._external_manifest_paths()

    assert str(paths["agent-service"]).endswith("apps/agent-service/src/models/permissions.py")


def test_builtin_tooling_feature_bundles_include_llm_provider_permissions():
    roles = {
        role["name"]: set(role["permissions"])
        for role in coarse_roles_migration.COARSE_ROLES_SEED
    }

    assert {
        "provider:create",
        "provider:delete",
        "provider:read",
        "provider:update",
    }.issubset(roles["tooling-admin"])
    assert "provider:read" in roles["tooling-user"]
