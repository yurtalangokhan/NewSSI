from schemas.users import UserProjectDetailResponse


def test_project_details_response_accepts_nested_project_payload() -> None:
    response = UserProjectDetailResponse.model_validate(
        {
            "project": {"id": 1, "name": "My Project", "chat_sessions": []},
            "files": [{"id": "file-1", "name": "drawing.png", "status": "COMPLETED"}],
            "persona_id_to_featured": {},
        }
    )

    assert response.project.id == 1
    assert response.project.name == "My Project"
    assert response.files[0]["status"] == "COMPLETED"
