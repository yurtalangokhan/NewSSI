from pydantic import TypeAdapter

from api.routes.user_route import router
from tests.envelope import envelope


def test_file_status_response_matches_service_list() -> None:
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/api/user/projects/file/statuses"
    )
    payload = [{"id": "file-1", "name": "drawing.png", "status": "COMPLETED"}]

    response = TypeAdapter(route.response_model).validate_python(envelope(payload))

    assert response.data[0].id == "file-1"
    assert response.data[0].status == "COMPLETED"
