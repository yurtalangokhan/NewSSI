from tests.unit_tests.fixtures import get_async_test_client

USER_1_HEADERS = {
    "Authorization": "Bearer user1",
}

USER_2_HEADERS = {
    "Authorization": "Bearer user2",
}


async def test_knowledge_selector_only_returns_current_user_visible_collections(
    monkeypatch,
) -> None:
    """Knowledge selector should not expose other users' private collections."""
    async def fake_graph_ids() -> list[str]:
        return []

    monkeypatch.setattr(
        "langconnect.api.datasources.GraphStore.list_graph_collection_ids",
        fake_graph_ids,
    )

    async with get_async_test_client() as client:
        user1_resp = await client.post(
            "/api/v1/collections",
            json={"name": "visible-user1", "metadata": {}},
            headers=USER_1_HEADERS,
        )
        assert user1_resp.status_code == 201

        user2_resp = await client.post(
            "/api/v1/collections",
            json={"name": "hidden-user2", "metadata": {}},
            headers=USER_2_HEADERS,
        )
        assert user2_resp.status_code == 201

        selector_resp = await client.get(
            "/api/v1/datasources/knowledge-selector",
            headers=USER_1_HEADERS,
        )
        assert selector_resp.status_code == 200

        names = {
            item["name"] for item in selector_resp.json()["document_processing"]
        }
        assert "visible-user1" in names
        assert "hidden-user2" not in names


async def test_knowledge_selector_omits_orphan_graph_collections(
    monkeypatch,
) -> None:
    """Graph ids without live collection metadata should not remain selectable."""
    async with get_async_test_client() as client:
        create_resp = await client.post(
            "/api/v1/collections",
            json={"name": "live-graph", "metadata": {}},
            headers=USER_1_HEADERS,
        )
        assert create_resp.status_code == 201
        live_id = create_resp.json()["uuid"]

        async def fake_graph_ids() -> list[str]:
            return [live_id, "00000000-0000-0000-0000-000000000000"]

        monkeypatch.setattr(
            "langconnect.api.datasources.GraphStore.list_graph_collection_ids",
            fake_graph_ids,
        )

        selector_resp = await client.get(
            "/api/v1/datasources/knowledge-selector",
            headers=USER_1_HEADERS,
        )
        assert selector_resp.status_code == 200

        graph_ids = {item["id"] for item in selector_resp.json()["knowledge_graph"]}
        assert live_id in graph_ids
        assert "00000000-0000-0000-0000-000000000000" not in graph_ids
