from tests.unit_tests.fixtures import get_async_test_client

USER_1_HEADERS = {
    "Authorization": "Bearer user1",
}


def idempotency_headers(base_headers: dict[str, str], key: str) -> dict[str, str]:
    return {**base_headers, "Idempotency-Key": key}


async def test_chunks_endpoint_paginates_large_files() -> None:
    async with get_async_test_client() as client:
        col_resp = await client.post(
            "/api/v1/collections",
            json={"name": "chunk_pagination_test", "metadata": {}},
            headers=idempotency_headers(USER_1_HEADERS, "chunks-pagination-col"),
        )
        assert col_resp.status_code == 201
        collection_id = col_resp.json()["uuid"]

        # A long text file splits into multiple chunks (TEXT_SPLITTER chunk_size=1000).
        long_content = ("Bu bir test cümlesidir. " * 200).encode("utf-8")
        files = [("files", ("long.txt", long_content, "text/plain"))]
        upload_resp = await client.post(
            f"/api/v1/collections/{collection_id}/documents",
            files=files,
            headers=idempotency_headers(USER_1_HEADERS, "chunks-pagination-upload"),
        )
        assert upload_resp.status_code == 200

        list_resp = await client.get(
            f"/api/v1/collections/{collection_id}/documents",
            headers=USER_1_HEADERS,
        )
        document_id = list_resp.json()[0]["id"]

        first_page = await client.get(
            f"/api/v1/collections/{collection_id}/documents/{document_id}/chunks",
            params={"limit": 2, "offset": 0},
            headers=USER_1_HEADERS,
        )
        assert first_page.status_code == 200
        page_data = first_page.json()
        assert len(page_data["chunks"]) == 2
        assert page_data["stats"]["total_chunks"] > 2
        assert page_data["total_chunks"] == page_data["stats"]["total_chunks"]
        assert page_data["has_more"] is True

        last_offset = page_data["total_chunks"] - 1
        last_page = await client.get(
            f"/api/v1/collections/{collection_id}/documents/{document_id}/chunks",
            params={"limit": 2, "offset": last_offset},
            headers=USER_1_HEADERS,
        )
        assert last_page.status_code == 200
        last_page_data = last_page.json()
        assert len(last_page_data["chunks"]) == 1
        assert last_page_data["has_more"] is False
