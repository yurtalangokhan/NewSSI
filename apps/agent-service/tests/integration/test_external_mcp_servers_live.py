"""Live acceptance test for the external MCP server infrastructure.

Exercises several *real* public MCP servers over the network:

* OAuth-protected servers  -> assert ``MCPOAuthService.discover`` can bootstrap
  an authorization-code flow (protected-resource + authorization-server
  metadata, PKCE, optional Dynamic Client Registration endpoint).
* Anonymous servers        -> connect, list tools, and actually *invoke*
  a read-only tool on each, asserting a usable result.

This is an integration test: it is excluded from ``make test`` (which ignores
``tests/integration``) and is additionally skipped unless
``RUN_LIVE_MCP_TESTS=1`` is set, because it needs outbound HTTPS and depends on
third-party uptime.

Run it explicitly::

    RUN_LIVE_MCP_TESTS=1 uv run pytest tests/integration/test_external_mcp_servers_live.py -v -s

TDD status: the ``oauth_discovery`` cases are RED until
``service.MCPOAuthService`` exists (plan task 4); the ``anonymous`` cases are
GREEN today and guard the runtime tool-loading path
(``MultiServerMCPClient``) the production loader uses.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_MCP_TESTS") != "1",
        reason="set RUN_LIVE_MCP_TESTS=1 to run live external-MCP acceptance tests",
    ),
]

HTTP_TIMEOUT = 30.0


# --------------------------------------------------------------------------- #
# OAuth-protected servers: only the discovery/bootstrap half is checkable
# headless (the consent redirect needs a human).
# --------------------------------------------------------------------------- #
OAUTH_SERVERS = [
    pytest.param(
        "https://api.githubcopilot.com/mcp/",
        True,  # strict: this server publishes complete, well-formed metadata
        id="github-copilot",
    ),
    pytest.param(
        "https://www.microsoft.com/releasecommunications/mcp",
        False,  # lenient: accept a *handled* MCPAuthError if metadata is partial
        id="microsoft-releasecommunications",
    ),
]


# --------------------------------------------------------------------------- #
# Anonymous servers.
#   LISTING cases  -> (url, expected tool-name subset)
#   INVOKE cases   -> (url, tool to call, call args)  -- only servers with a
#                     stable, well-documented read-only tool
# --------------------------------------------------------------------------- #
ANON_LISTING = [
    pytest.param(
        "https://mcp.deepwiki.com/mcp",
        {"read_wiki_structure", "read_wiki_contents", "ask_question"},
        id="deepwiki",
    ),
    pytest.param(
        "https://learn.microsoft.com/api/mcp",
        {"microsoft_docs_search"},
        id="microsoft-learn",
    ),
    pytest.param(
        "https://mcp.context7.com/mcp",
        {"resolve-library-id"},
        id="context7",
    ),
]

ANON_INVOKE = [
    pytest.param(
        "https://mcp.deepwiki.com/mcp",
        "read_wiki_structure",
        {"repoName": "facebook/react"},
        id="deepwiki-read_wiki_structure",
    ),
    pytest.param(
        "https://learn.microsoft.com/api/mcp",
        "microsoft_docs_search",
        {"query": "what is azure functions"},
        id="microsoft-learn-microsoft_docs_search",
    ),
]


def _connection(url: str, headers: dict[str, str] | None = None) -> dict:
    conn: dict = {"transport": "streamable_http", "url": url, "timeout": HTTP_TIMEOUT}
    if headers:
        conn["headers"] = headers
    return conn


async def _list_tools(url: str, headers: dict[str, str] | None = None):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({"live": _connection(url, headers)})
    return await client.get_tools()


# --------------------------------------------------------------------------- #
# OAuth discovery tier  (RED until MCPOAuthService lands)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("server_url, strict", OAUTH_SERVERS)
async def test_oauth_discovery_bootstraps_authorization_flow(server_url: str, strict: bool):
    from service.MCPCredentialService import MCPAuthError
    from service.MCPOAuthService import MCPOAuthService

    svc = MCPOAuthService()

    try:
        metadata = await svc.discover(server_url)
    except MCPAuthError as exc:
        if strict:
            raise
        # A partial/quirky server is acceptable *iff* the failure is one our
        # code raised deliberately with an actionable message.
        msg = str(exc).lower()
        assert any(k in msg for k in ("discovery failed", "manual client registration", "oauth")), (
            exc
        )
        return

    assert metadata["authorization_endpoint"].startswith("https://"), metadata
    assert metadata["token_endpoint"].startswith("https://"), metadata
    # RFC 8707 resource identifier is needed for the authorization request.
    assert metadata.get("resource"), metadata

    # We can construct a real authorization URL without a client secret when the
    # server supports Dynamic Client Registration; otherwise ensure_client must
    # tell the caller to supply one.
    if metadata.get("registration_endpoint"):
        assert metadata["registration_endpoint"].startswith("https://")


# --------------------------------------------------------------------------- #
# Anonymous tier  (GREEN today)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("server_url, expected_subset", ANON_LISTING)
async def test_anonymous_server_lists_expected_tools(server_url: str, expected_subset: set[str]):
    tools = await _list_tools(server_url)
    names = {t.name for t in tools}

    assert tools, f"{server_url} exposed no tools"
    assert expected_subset <= names, (
        f"{server_url}: expected {expected_subset}, got {sorted(names)}"
    )


@pytest.mark.parametrize("server_url, call_tool, call_args", ANON_INVOKE)
async def test_anonymous_server_runs_a_read_only_tool(
    server_url: str, call_tool: str, call_args: dict
):
    tools = await _list_tools(server_url)
    tool = next((t for t in tools if t.name == call_tool), None)
    assert tool is not None, (
        f"{server_url} no longer exposes {call_tool}: {sorted(t.name for t in tools)}"
    )

    result = await tool.ainvoke(call_args)

    text = result if isinstance(result, str) else str(result)
    assert text.strip(), f"{call_tool} on {server_url} returned an empty result"


# --------------------------------------------------------------------------- #
# Human-readable summary of what actually connected (use -s to see it).
# --------------------------------------------------------------------------- #
async def test_print_infra_reachability_summary(capsys):
    lines: list[str] = ["", "external MCP reachability:"]

    for p in OAUTH_SERVERS:
        url = p.values[0]
        status = "?"
        try:
            from service.MCPOAuthService import MCPOAuthService

            md = await MCPOAuthService().discover(url)
            status = f"oauth ok  (authz={md['authorization_endpoint']}, dcr={'yes' if md.get('registration_endpoint') else 'no'})"
        except ModuleNotFoundError:
            status = "oauth service not implemented yet (RED)"
        except Exception as exc:  # noqa: BLE001 - summary only
            status = f"oauth discovery error: {exc}"
        lines.append(f"  {url}\n      {status}")

    for p in ANON_LISTING:
        url = p.values[0]
        try:
            tools = await _list_tools(url)
            lines.append(
                f"  {url}\n      anon ok   ({len(tools)} tools: {', '.join(sorted(t.name for t in tools)[:6])})"
            )
        except Exception as exc:  # noqa: BLE001 - summary only
            lines.append(f"  {url}\n      anon error: {exc}")

    with capsys.disabled():
        print("\n".join(lines))
