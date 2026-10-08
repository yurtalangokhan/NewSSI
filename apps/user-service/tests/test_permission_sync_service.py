import importlib

coarse_roles_migration = importlib.import_module(
    "src.core.database.migrations.versions.0010_add_coarse_roles"
)


def test_builtin_tooling_feature_bundles_include_llm_provider_permissions():
    roles = {
        role["name"]: set(role["permissions"]) for role in coarse_roles_migration.COARSE_ROLES_SEED
    }

    assert {
        "provider:create",
        "provider:delete",
        "provider:read",
        "provider:update",
    }.issubset(roles["tooling-admin"])
    assert "provider:read" in roles["tooling-user"]
