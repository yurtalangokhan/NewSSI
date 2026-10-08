"""limit=1000000 was accepted on GET /api/v1/users, and a search term
containing % or _ silently widened the LIKE query. Spec T4."""

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from error_contract import register_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.user_route import router as user_router
from tests.route_support import override_route_dependencies


def test_limit_query_is_bounded():
    from src.api.routes import user_route

    assert user_route.MAX_PAGE_SIZE <= 200
    source = inspect.getsource(user_route)
    assert "le=MAX_PAGE_SIZE" in source


@pytest.fixture
def app():
    app = FastAPI()
    register_error_handlers(app, service_name="user-service-test")
    app.include_router(user_router, prefix="/api/v1")
    override_route_dependencies(app, lambda: str(uuid.uuid4()))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _mock_controller():
    controller = MagicMock()
    controller.list_users = AsyncMock(return_value={"users": [], "total": 0, "total_exact": True})
    with patch("src.api.routes.user_route.get_user_controller", return_value=controller):
        yield controller


@pytest.mark.parametrize("limit", [201, 10_000, 1_000_000])
def test_oversized_limit_is_rejected(client: TestClient, limit):
    response = client.get(f"/api/v1/users/?limit={limit}")
    assert response.status_code == 422


@pytest.mark.parametrize("page_size", [201, 10_000, 1_000_000])
def test_oversized_page_size_is_rejected(client: TestClient, page_size):
    response = client.get(f"/api/v1/users/?page_size={page_size}")
    assert response.status_code == 422


def test_limit_within_bounds_is_accepted(client: TestClient):
    response = client.get("/api/v1/users/?limit=50")
    assert response.status_code == 200


def test_page_num_zero_is_accepted(client: TestClient):
    """The frontend's usePaginatedFetch hook is 0-indexed and requests
    page_num=0 for the first page; the endpoint must accept it."""
    response = client.get("/api/v1/users/?page_num=0&page_size=20")
    assert response.status_code == 200


def test_page_num_negative_is_rejected(client: TestClient):
    response = client.get("/api/v1/users/?page_num=-1&page_size=20")
    assert response.status_code == 422


@pytest.mark.parametrize("term", ["100%", "a_b", "a\\b"])
def test_sql_wildcards_are_literal_directory_search_characters(term):
    from src.repository.user_repository import UserRepository

    matches = UserRepository._term_predicate(term)
    assert matches(term)
    assert not matches(term.replace("%", "x").replace("_", "x").replace("\\", "x"))
