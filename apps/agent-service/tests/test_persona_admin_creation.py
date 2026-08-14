from api.routes import PersonaRoute


def test_persona_routes_do_not_expose_role_name_admin_gate() -> None:
    assert not hasattr(PersonaRoute, "_require_admin")


def test_create_persona_route_requires_persona_create_permission() -> None:
    create_route = next(
        route
        for route in PersonaRoute.router.routes
        if getattr(route, "path", None) == "/api/persona"
        and "POST" in getattr(route, "methods", set())
    )

    dependency_names = [
        getattr(dependency.call, "__name__", "")
        for dependency in getattr(create_route, "dependant").dependencies
    ]

    assert "_check_permission" in dependency_names
