from pydantic import TypeAdapter

from api.routes.user_route import router
from tests.envelope import envelope


def test_project_upload_response_matches_service_envelope() -> None:
    route = next(
        route
        for route in router.routes
        if getattr(route, "path", None) == "/api/user/projects/file/upload"
    )
    payload = {
        "user_files": [{"id": "file-1", "name": "report.pdf", "status": "COMPLETED"}],
        "rejected_files": [],
    }

    response = TypeAdapter(route.response_model).validate_python(envelope(payload))

    assert response.data.user_files[0].id == "file-1"
    assert response.data.rejected_files == []
