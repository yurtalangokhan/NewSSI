"""Tests for options resolvers.

Per-source logic tests call the private ``_resolve_*`` function directly with
an injected fake repository — the real service class runs for real (masking,
filtering, mapping), only the DB-touching boundary is faked. Cross-cutting
concerns (dispatch, caching, isolation, failure handling) are tested through
the public ``resolve_options`` with a source's resolver swapped via
``monkeypatch.setitem`` on the dispatch table, restored automatically after
each test.

Spec: .tmp/flow-canvas-design.md section 4.2.
Brief: .tmp/flow-canvas-task-5-brief.md
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.exceptions import UnknownOptionsSourceError
from domain.flows import resolvers
from domain.flows.resolvers import (
    OptionItem,
    ResolverContext,
    is_flow_backed,
    resolve_options,
)
from domain.flows.sources import KNOWN_OPTIONS_SOURCES


@pytest.fixture(autouse=True)
def _clear_cache():
    resolvers.clear_cache()
    yield
    resolvers.clear_cache()


# ---------------------------------------------------------------------------
# Fakes — stub the transport (repo), not the service's own logic
# ---------------------------------------------------------------------------


class _FakeMailConfigRepo:
    def __init__(self, rows_by_user: dict[str, list[dict]]):
        self._rows_by_user = rows_by_user

    async def list_active(
        self,
        search: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[dict]:
        """Every active config, whoever owns it.

        Mail configs are administered centrally and each user binds their own
        SMTP credentials to one, so the selectable set is not owner-scoped.
        """
        out: list[dict] = []
        for rows in self._rows_by_user.values():
            out.extend(row for row in rows if row.get("is_active", True))
        return out

    async def list_by_user_ids(self, user_ids) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for user_id in user_ids or []:
            for row in self._rows_by_user.get(str(user_id), []):
                if row["id"] not in seen:
                    seen.add(row["id"])
                    out.append(row)
        return out


class _FakeMCPToolRepo:
    def __init__(self, categories: dict[str, list[dict]]):
        self._categories = categories

    async def list_categories(self) -> list[str]:
        return list(self._categories)

    async def get_by_category(self, category: str) -> list[dict]:
        return self._categories.get(category, [])


@dataclass
class _FakeDefinition:
    id: object
    name: str
    graph_schema: str
    persona_id: int | None = None
    model: str | None = None
    mcp_tools: list | None = None
    memory_type: str | None = None
    system_prompt: str | None = None


class _FakeAgentDefRepo:
    def __init__(self, definitions: list[_FakeDefinition]):
        self._definitions = definitions

    async def list_all(self, graph_schema: str | None = None, active_only: bool = True):
        return self._definitions

    async def get_by_id(self, definition_id):
        return next((d for d in self._definitions if d.id == definition_id), None)


class _FakePersonaRepo:
    def __init__(self, personas: list[dict]):
        self._personas = personas

    async def list_all(self) -> list[dict]:
        return self._personas


# ---------------------------------------------------------------------------
# 5.1 — shape of a resolved option, via a real service + fake repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_options_for_known_source():
    repo = _FakeMailConfigRepo(
        {"user-1": [{"id": "cfg-1", "name": "Primary SMTP", "is_active": True}]}
    )

    items = await resolvers._resolve_mail_configs(
        ResolverContext(user_id="user-1"), service=_mail_service(repo)
    )

    assert items == [OptionItem(value="cfg-1", label="Primary SMTP")]


# ---------------------------------------------------------------------------
# 5.2 — unknown source
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_raises_for_unknown_source_key():
    with pytest.raises(UnknownOptionsSourceError) as exc:
        await resolve_options("nope.nope", ResolverContext(user_id="u1"))

    assert "nope.nope" in str(exc.value)


# ---------------------------------------------------------------------------
# 5.3 — structural guard: every declared source has a resolver
# ---------------------------------------------------------------------------


def test_every_options_source_declared_in_registry_has_a_resolver():
    for source in KNOWN_OPTIONS_SOURCES:
        assert source in resolvers._RESOLVERS, f"no resolver registered for {source!r}"


# ---------------------------------------------------------------------------
# 5.4 — isolation: one user must never see another user's resources
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mail_config_options_are_the_shared_admin_catalog():
    repo = _FakeMailConfigRepo(
        {
            "user-a": [{"id": "cfg-a", "name": "A's config", "is_active": True}],
            "user-b": [{"id": "cfg-b", "name": "B's config", "is_active": True}],
        }
    )
    service = _mail_service(repo)

    items_a = await resolvers._resolve_mail_configs(
        ResolverContext(user_id="user-a"), service=service
    )
    items_b = await resolvers._resolve_mail_configs(
        ResolverContext(user_id="user-b"), service=service
    )

    # Centrally administered SMTP servers: both callers can select either one
    # and supply their own credentials for it.
    assert [i.value for i in items_a] == ["cfg-a", "cfg-b"]
    assert [i.value for i in items_b] == ["cfg-a", "cfg-b"]


# ---------------------------------------------------------------------------
# 5.5 / 5.7 — caching, keyed by (source, user_id)
# ---------------------------------------------------------------------------


def _counting_resolver():
    calls: list[str] = []

    async def fake(context: ResolverContext) -> list[OptionItem]:
        calls.append(context.user_id)
        return [OptionItem(value="x", label="X")]

    return fake, calls


@pytest.mark.asyncio
async def test_results_are_cached_per_user_for_ttl(monkeypatch):
    fake, calls = _counting_resolver()
    monkeypatch.setitem(resolvers._RESOLVERS, "mail.configs", fake)

    context = ResolverContext(user_id="same-user")
    await resolve_options("mail.configs", context)
    await resolve_options("mail.configs", context)

    assert calls == ["same-user"]  # second call served from cache


@pytest.mark.asyncio
async def test_cache_key_includes_user_id(monkeypatch):
    fake, calls = _counting_resolver()
    monkeypatch.setitem(resolvers._RESOLVERS, "mail.configs", fake)

    await resolve_options("mail.configs", ResolverContext(user_id="user-a"))
    await resolve_options("mail.configs", ResolverContext(user_id="user-b"))

    assert calls == ["user-a", "user-b"]  # no cross-user cache hit


# ---------------------------------------------------------------------------
# 5.6 — upstream failure isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upstream_failure_yields_empty_options_not_an_exception(monkeypatch):
    async def failing(context: ResolverContext) -> list[OptionItem]:
        raise ConnectionError("rag-service unreachable")

    monkeypatch.setitem(resolvers._RESOLVERS, "rag.collections", failing)

    result = await resolve_options("rag.collections", ResolverContext(user_id="u1"))

    assert result.available is False
    assert result.items == []


# ---------------------------------------------------------------------------
# 5.8 — mail configs: active only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mail_configs_excludes_inactive():
    repo = _FakeMailConfigRepo(
        {
            "user-1": [
                {"id": "cfg-active", "name": "Active", "is_active": True},
                {"id": "cfg-inactive", "name": "Inactive", "is_active": False},
            ]
        }
    )

    items = await resolvers._resolve_mail_configs(
        ResolverContext(user_id="user-1"), service=_mail_service(repo)
    )

    assert [i.value for i in items] == ["cfg-active"]


# ---------------------------------------------------------------------------
# 5.9 — agent definitions exclude flow-backed agents (design spec 5.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_definitions_excludes_flow_backed_agents():
    definitions = [
        _FakeDefinition(id=uuid4(), name="Classic ReAct", graph_schema="react"),
        _FakeDefinition(id=uuid4(), name="A Flow", graph_schema="flow"),
    ]

    from domain.agents.service import AgentDefinitionService

    items = await resolvers._resolve_agent_definitions(
        ResolverContext(user_id="u1"),
        service=AgentDefinitionService(_FakeAgentDefRepo(definitions)),
    )

    assert [i.label for i in items] == ["Classic ReAct"]


@pytest.mark.asyncio
async def test_agent_definitions_use_persona_display_name_when_linked():
    definitions = [
        _FakeDefinition(id=uuid4(), name="persona-15", graph_schema="react", persona_id=15),
    ]

    from domain.agents.service import AgentDefinitionService

    items = await resolvers._resolve_agent_definitions(
        ResolverContext(user_id="u1"),
        service=AgentDefinitionService(_FakeAgentDefRepo(definitions)),
        persona_repo=_FakePersonaRepo([{"id": 15, "name": "Support Bot"}]),
    )

    assert [i.label for i in items] == ["Support Bot"]


@pytest.mark.asyncio
async def test_agent_definitions_fall_back_to_definition_name_without_persona_link():
    definitions = [
        _FakeDefinition(
            id=uuid4(), name="Manual Definition", graph_schema="react", persona_id=None
        ),
    ]

    from domain.agents.service import AgentDefinitionService

    items = await resolvers._resolve_agent_definitions(
        ResolverContext(user_id="u1"),
        service=AgentDefinitionService(_FakeAgentDefRepo(definitions)),
        persona_repo=_FakePersonaRepo([]),
    )

    assert [i.label for i in items] == ["Manual Definition"]


@pytest.mark.asyncio
async def test_agent_definitions_description_carries_hover_preview():
    definitions = [
        _FakeDefinition(
            id=uuid4(),
            name="persona-7",
            graph_schema="react",
            persona_id=7,
            model="gpt-4o",
            mcp_tools=["file_read"],
            memory_type="long_term",
        ),
    ]

    from domain.agents.service import AgentDefinitionService

    items = await resolvers._resolve_agent_definitions(
        ResolverContext(user_id="u1"),
        service=AgentDefinitionService(_FakeAgentDefRepo(definitions)),
        persona_repo=_FakePersonaRepo([{"id": 7, "name": "Research Agent"}]),
    )

    assert "gpt-4o" in items[0].description
    assert "Tools: 1" in items[0].description


# ---------------------------------------------------------------------------
# 5.10 — MCP tools grouped by category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_are_grouped_by_category():
    from service.MCPToolService import MCPToolService

    repo = _FakeMCPToolRepo(
        {
            "file": [{"name": "file_read", "display_name": "Read File"}],
            "git": [{"name": "git_status", "display_name": "Git Status"}],
        }
    )

    items = await resolvers._resolve_mcp_tools_by_category(
        ResolverContext(user_id="u1"),
        service=MCPToolService(tool_repo=repo),
    )

    categories = {i.description for i in items}
    assert categories == {"file", "git"}
    assert {i.value for i in items} == {"file_read", "git_status"}


# ---------------------------------------------------------------------------
# external MCP provider tools — canvas ExternalMCPServer node tool picker
# ---------------------------------------------------------------------------


class _FakeMCPProviderService:
    def __init__(self, providers: list[dict]):
        self._providers = providers

    async def list_providers(self, include_inactive: bool = False) -> list[dict]:
        return self._providers


class _FakeMCPProviderToolService:
    def __init__(self, tools_by_provider: dict[str, list[dict]]):
        self._tools_by_provider = tools_by_provider

    async def list_tools_by_provider(
        self, provider_id: str, include_inactive: bool = False
    ) -> list[dict]:
        return self._tools_by_provider.get(provider_id, [])


@pytest.mark.asyncio
async def test_mcp_external_tools_are_qualified_and_tagged_with_their_provider():
    provider_service = _FakeMCPProviderService(
        [
            {"id": "prov-1", "name": "DeepWiki", "type": "external"},
            {"id": "prov-2", "name": "Local Files", "type": "builtin"},
        ]
    )
    tool_service = _FakeMCPProviderToolService(
        {
            "prov-1": [
                {"name": "ask_question", "description": "Ask a question about a repo"},
            ],
            "prov-2": [
                {"name": "file_read", "description": "Read a file"},
            ],
        }
    )

    items = await resolvers._resolve_mcp_external_tools(
        ResolverContext(user_id="u1"),
        provider_service=provider_service,
        tool_service=tool_service,
    )

    # only the external provider's tools, qualified by server slug
    assert [i.value for i in items] == ["deepwiki__ask_question"]
    assert items[0].label == "ask_question"
    # description carries "<provider_id>|<tool description>" so the canvas
    # multiselect can filter to the provider selected on the same node
    assert items[0].description == "prov-1|Ask a question about a repo"


# ---------------------------------------------------------------------------
# 5.11 — is_flow_backed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_flow_backed_identifies_flow_definitions():
    flow_id = uuid4()
    classic_id = uuid4()
    repo = _FakeAgentDefRepo(
        [
            _FakeDefinition(id=flow_id, name="Flow", graph_schema="flow"),
            _FakeDefinition(id=classic_id, name="Classic", graph_schema="react"),
        ]
    )

    assert await is_flow_backed(str(flow_id), repo=repo) is True
    assert await is_flow_backed(str(classic_id), repo=repo) is False
    assert await is_flow_backed("not-a-uuid", repo=repo) is False


# ---------------------------------------------------------------------------
# 5.12 — resource reference validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resource_reference_validation_flags_missing_collection(monkeypatch):
    async def fake(context: ResolverContext) -> list[OptionItem]:
        return [OptionItem(value="col-1", label="Collection One")]

    monkeypatch.setitem(resolvers._RESOLVERS, "rag.collections", fake)
    context = ResolverContext(user_id="u1")

    assert await resolvers.resource_exists("rag.collections", "col-1", context) is True
    assert await resolvers.resource_exists("rag.collections", "col-999", context) is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mail_service(repo):
    from service.MailConfigService import MailConfigService

    return MailConfigService(repo=repo)


# ---------------------------------------------------------------------------
# Task 49 — datasources and web search resolvers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_datasources_maps_id_and_name():
    """49.1 — _resolve_datasources maps datasource rows to OptionItems."""
    mock_ctrl = MagicMock()
    mock_ctrl.list_datasources = AsyncMock(
        return_value=[
            {"id": "ds-1", "name": "Postgres DB", "connector_display_name": "PostgreSQL"},
            {"id": "ds-2", "name": "Notion Docs", "connector_display_name": "Notion"},
        ]
    )

    ctx = ResolverContext(user_id="u-1")
    items = await resolvers._resolve_datasources(ctx, controller=mock_ctrl)
    assert len(items) == 2
    assert items[0].value == "ds-1"
    assert items[0].label == "Postgres DB"
    assert items[1].value == "ds-2"
    assert items[1].label == "Notion Docs"


@pytest.mark.asyncio
async def test_resolve_datasources_empty_when_no_datasources():
    """49.2 — _resolve_datasources returns empty list when none exist."""
    mock_ctrl = MagicMock()
    mock_ctrl.list_datasources = AsyncMock(return_value=[])

    ctx = ResolverContext(user_id="u-1")
    items = await resolvers._resolve_datasources(ctx, controller=mock_ctrl)
    assert items == []


@pytest.mark.asyncio
async def test_resolve_websearch_providers_returns_empty_list_cleanly():
    """49.3 — _resolve_websearch_providers calls controller and returns empty list cleanly."""
    mock_ctrl = MagicMock()
    mock_ctrl.list_search_providers = MagicMock(return_value=[])

    ctx = ResolverContext(user_id="u-1")
    items = await resolvers._resolve_websearch_providers(ctx, controller=mock_ctrl)
    assert items == []


@pytest.mark.asyncio
async def test_resolve_websearch_content_providers_returns_atlas_crawler():
    """49.4 — _resolve_websearch_content_providers returns ATLAS Web Crawler option."""
    mock_ctrl = MagicMock()
    mock_ctrl.list_content_providers = MagicMock(
        return_value=[{"id": 1, "name": "ATLAS Web Crawler", "provider_type": "atlas_web_crawler"}]
    )

    ctx = ResolverContext(user_id="u-1")
    items = await resolvers._resolve_websearch_content_providers(ctx, controller=mock_ctrl)
    assert len(items) == 1
    assert items[0].value == "atlas_web_crawler"
    assert items[0].label == "ATLAS Web Crawler"


@pytest.mark.asyncio
async def test_resolve_datasources_upstream_failure_degrades_to_unavailable():
    """49.5 — Upstream error in list_datasources degrades gracefully to available=False."""
    with patch("controller.get_data_controller") as mock_get:
        mock_ctrl = MagicMock()
        mock_ctrl.list_datasources = AsyncMock(side_effect=RuntimeError("DB unreachable"))
        mock_get.return_value = mock_ctrl

        ctx = ResolverContext(user_id="u-1")
        res = await resolve_options("datasources.list", ctx)
        assert res.available is False
        assert res.items == []


# ---------------------------------------------------------------------------
# _BUILTIN_CATEGORY_TOOLS — the fallback used when the DB-backed tool cache
# (mcp_tool table, synced via MCPToolService) is empty, which today it always
# is (nothing ever calls sync_tools_from_provider in this environment). Every
# flow using an MCP tool category currently goes through this static list, so
# a wrong name here silently breaks the tool at runtime (WebTools/etc. select
# fine in the editor, then AssistantAgentService's _get_tools_for_names logs
# "not found in tools map" and drops it) while validation reports nothing
# wrong. Values below were checked against the live tools service's real
# tool names (each tool's description carries its own real
# [category:...][title:...] tag) — this locks that in as a regression test.
# ---------------------------------------------------------------------------


def test_builtin_category_tools_web_matches_the_live_server_names():
    """web previously listed fetch_web_page/search_web — the real server
    calls them fetch_webpage/web_search (and reversed word order)."""
    values = {item.value for item in resolvers._BUILTIN_CATEGORY_TOOLS["web"]}
    assert values == {"fetch_webpage", "web_search"}


def test_builtin_category_tools_calculator_matches_the_live_server_names():
    values = {item.value for item in resolvers._BUILTIN_CATEGORY_TOOLS["calculator"]}
    assert values == {"calculate"}


def test_builtin_category_tools_has_no_duplicate_values_within_a_category():
    for category, items in resolvers._BUILTIN_CATEGORY_TOOLS.items():
        values = [item.value for item in items]
        assert len(values) == len(set(values)), f"duplicate tool value in category '{category}'"


def test_builtin_category_tools_has_an_entry_for_every_declared_category():
    from domain.flows.resolvers import _MCP_CATEGORIES

    for category in _MCP_CATEGORIES:
        assert category in resolvers._BUILTIN_CATEGORY_TOOLS
        assert len(resolvers._BUILTIN_CATEGORY_TOOLS[category]) > 0, (
            f"category '{category}' has no tool options"
        )


def test_rag_urls_come_from_the_shared_transport_contract(monkeypatch):
    """The resolvers used to keep their own base-URL rule, whose fallback was
    an empty string — so with `RAG_API_URL` unset every dropdown built a
    host-less URL, failed, and silently degraded to the DB fallback. The rule
    now lives in `client.rag_http` alongside the flow compiler's."""
    from client.rag_http import DEFAULT_RAG_BASE_URL
    from core import env as env_module

    monkeypatch.delenv("RAG_API_URL", raising=False)
    monkeypatch.delenv("RAG_SERVICE_API_URL", raising=False)
    env_module.env._cache.clear()
    try:
        assert resolvers.rag_url("/collections") == f"{DEFAULT_RAG_BASE_URL}/api/v1/collections"
    finally:
        env_module.env._cache.clear()


# ---------------------------------------------------------------------------
# flows.published (Phase 5) — Run Flow's target list
# ---------------------------------------------------------------------------


class _PublishedFlowDef:
    def __init__(self, id_, name, graph_schema, flow_spec, persona_id=None):
        self.id = id_
        self.name = name
        self.graph_schema = graph_schema
        self.flow_spec = flow_spec
        self.persona_id = persona_id


class _PublishedFlowDefRepo:
    def __init__(self, definitions):
        self._definitions = definitions
        self.calls: list[dict] = []

    async def list_all(self, **kwargs):
        self.calls.append(kwargs)
        schema = kwargs.get("graph_schema")
        if schema:
            return [d for d in self._definitions if d.graph_schema == schema]
        return list(self._definitions)


@pytest.mark.asyncio
async def test_flows_published_lists_only_published_flow_backed_definitions(monkeypatch):
    """`flow_spec` on a definition is the denormalized cache of the *published*
    version, so a non-null value is exactly "has a published version". A draft
    that was never published cannot be compiled and must not be offered."""
    repo = _PublishedFlowDefRepo(
        [
            _PublishedFlowDef("1", "Published flow", "flow", {"nodes": [], "edges": []}),
            _PublishedFlowDef("2", "Draft only", "flow", None),
            _PublishedFlowDef("3", "Classic agent", "zero_shot", None),
        ]
    )
    monkeypatch.setattr(resolvers, "_flow_definition_repository", lambda: repo)
    resolvers._cache.clear()

    result = await resolve_options("flows.published", ResolverContext(user_id="u1"))

    assert [i.value for i in result.items] == ["1"]
    assert result.items[0].label == "Published flow"


@pytest.mark.asyncio
async def test_flows_published_uses_persona_display_name_when_linked(monkeypatch):
    """A persona-linked definition's ``name`` is only an internal placeholder
    (e.g. "persona-50"); the Run Flow dropdown must show the persona's real
    display name, falling back to ``d.name`` when there is no persona link."""
    repo = _PublishedFlowDefRepo(
        [
            _PublishedFlowDef("1", "persona-50", "flow", {"nodes": [], "edges": []}, persona_id=50),
            _PublishedFlowDef("2", "Hand-named flow", "flow", {"nodes": [], "edges": []}),
        ]
    )
    monkeypatch.setattr(resolvers, "_flow_definition_repository", lambda: repo)

    items = await resolvers._resolve_published_flows(
        ResolverContext(user_id="u1"),
        persona_repo=_FakePersonaRepo([{"id": 50, "name": "Onboarding Assistant"}]),
    )

    assert [i.label for i in items] == ["Onboarding Assistant", "Hand-named flow"]


@pytest.mark.asyncio
async def test_flows_published_is_a_known_source():
    assert "flows.published" in KNOWN_OPTIONS_SOURCES


# ---------------------------------------------------------------------------
# options_source dependencies
#
# Before this, `llm.models` returned every provider's models and the canvas
# filtered them client-side by splitting the `description` string on "|" with
# a two-way substring match. That is the Phase 0 route/label bug again: a
# contract encoded in a display field, special-cased on one side of the wire.
# ---------------------------------------------------------------------------


class _ProviderModelService:
    """Stands in for ProviderService.get_available_models_for_user."""

    def __init__(self):
        self.calls = 0

    async def get_available_models_for_user(self, user_id):
        self.calls += 1
        return [
            {
                "id": "openai",
                "provider": "openai",
                "provider_display_name": "OpenAI",
                "model_configurations": [
                    {"name": "gpt-4o", "display_name": "GPT-4o"},
                    {"name": "gpt-4o-mini", "display_name": "GPT-4o mini"},
                ],
            },
            {
                "id": "anthropic",
                "provider": "anthropic",
                "provider_display_name": "Anthropic",
                "model_configurations": [{"name": "claude-opus", "display_name": "Claude Opus"}],
            },
        ]


def test_resolver_context_carries_no_dependencies_by_default():
    assert ResolverContext(user_id="u1").depends == {}


@pytest.mark.asyncio
async def test_llm_models_are_unfiltered_when_no_provider_is_chosen():
    items = await resolvers._resolve_llm_models(
        ResolverContext(user_id="u1"), service=_ProviderModelService()
    )
    assert {i.value for i in items} == {"gpt-4o", "gpt-4o-mini", "claude-opus"}


@pytest.mark.asyncio
async def test_llm_models_are_filtered_by_the_chosen_provider():
    items = await resolvers._resolve_llm_models(
        ResolverContext(user_id="u1", depends={"provider": "openai"}),
        service=_ProviderModelService(),
    )
    assert {i.value for i in items} == {"gpt-4o", "gpt-4o-mini"}


@pytest.mark.asyncio
async def test_a_provider_that_matches_nothing_yields_an_empty_list():
    """Deliberately NOT a fallback to every model. Showing another provider's
    models lets an author pick one that cannot run, and the failure only
    surfaces at run time."""
    items = await resolvers._resolve_llm_models(
        ResolverContext(user_id="u1", depends={"provider": "nosuch"}),
        service=_ProviderModelService(),
    )
    assert items == []


@pytest.mark.asyncio
async def test_the_filter_matches_the_provider_id_exactly_not_by_substring():
    """The old client-side filter matched `a in b or b in a`, so "openai"
    also matched an "openai-compatible" provider and vice versa."""

    class _Overlapping:
        async def get_available_models_for_user(self, user_id):
            return [
                {
                    "id": "openai",
                    "provider": "openai",
                    "provider_display_name": "OpenAI",
                    "model_configurations": [{"name": "gpt-4o"}],
                },
                {
                    "id": "openai-compatible",
                    "provider": "openai-compatible",
                    "provider_display_name": "Self-hosted",
                    "model_configurations": [{"name": "yerel-model"}],
                },
            ]

    items = await resolvers._resolve_llm_models(
        ResolverContext(user_id="u1", depends={"provider": "openai"}), service=_Overlapping()
    )
    assert {i.value for i in items} == {"gpt-4o"}


@pytest.mark.asyncio
async def test_the_cache_is_keyed_by_the_dependency_values(monkeypatch):
    """The bug this guards against is invisible without it: resolving for
    provider A would warm a cache that then serves provider A's models to
    provider B."""
    service = _ProviderModelService()
    monkeypatch.setitem(
        resolvers._RESOLVERS,
        "llm.models",
        lambda ctx: resolvers._resolve_llm_models(ctx, service=service),
    )
    resolvers._cache.clear()

    first = await resolve_options(
        "llm.models", ResolverContext(user_id="u1", depends={"provider": "openai"})
    )
    second = await resolve_options(
        "llm.models", ResolverContext(user_id="u1", depends={"provider": "anthropic"})
    )

    assert {i.value for i in first.items} == {"gpt-4o", "gpt-4o-mini"}
    assert {i.value for i in second.items} == {"claude-opus"}


@pytest.mark.asyncio
async def test_the_same_dependencies_still_hit_the_cache(monkeypatch):
    service = _ProviderModelService()
    monkeypatch.setitem(
        resolvers._RESOLVERS,
        "llm.models",
        lambda ctx: resolvers._resolve_llm_models(ctx, service=service),
    )
    resolvers._cache.clear()

    ctx = ResolverContext(user_id="u1", depends={"provider": "openai"})
    await resolve_options("llm.models", ctx)
    await resolve_options("llm.models", ctx)
    assert service.calls == 1
