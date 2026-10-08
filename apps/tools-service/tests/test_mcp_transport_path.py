"""The MCP transport must answer at the bare ``/mcp`` path.

MCP clients (the ``mcp`` SDK over httpx) POST JSON-RPC to the configured URL
and do not follow redirects. A ``307 -> /mcp/`` therefore breaks every
consumer, including agent-service tool discovery, while looking harmless to a
redirect-following test client.
"""


def test_mcp_post_is_served_at_bare_path_without_redirect(http_client) -> None:
    response = http_client.post("/mcp", follow_redirects=False)

    assert response.status_code != 307, (
        f"POST /mcp redirected to {response.headers.get('location')}; "
        "MCP clients do not follow redirects"
    )
    # Reaching the transport means reaching its auth layer.
    assert response.status_code in {401, 403}
