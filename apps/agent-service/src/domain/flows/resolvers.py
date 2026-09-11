"""Dynamic option resolvers.

Turn a template's declared ``options_source`` key into the calling user's
real, live data — the RAG collection dropdown lists the user's actual
collections, the MCP tool multiselect lists tools-service's actual tools.

Results are cached 30s, keyed by ``(source, user_id)`` — never by source
alone, which would leak one user's visible resources into another user's
dropdown. An unreachable upstream degrades a single field to "unavailable"
rather than failing the whole sidebar.

See ``.tmp/flow-canvas-design.md`` section 4.2.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from agents.graphs.schemas import GraphSchemaType
from client.rag_http import rag_url
from core.exceptions import UnknownOptionsSourceError
from core.logger import get_logger
from domain.flows.mcp_catalog import MCP_CATEGORIES, MCP_CATEGORY_KEYS
from domain.flows.sources import KNOWN_OPTIONS_SOURCES

logger = get_logger(__name__)

_CACHE_TTL_SECONDS = 30.0
# Upstream (rag-service / Ollama) HTTP call budget for a single dropdown resolve.
_RESOLVER_HTTP_TIMEOUT_SECONDS = 10.0
# rag-service REST prefix; every collection/datasource call shares it.
# The seed collection every tenant gets — never shown as a user-selectable option.
_DEFAULT_COLLECTION_NAME = "default_collection"
# A canonical UUID rendered as a string is exactly this long ("8-4-4-4-12").
_UUID_STRING_LENGTH = 36


@dataclass(frozen=True)
class ResolverContext:
    """Who is asking, and in what situation.

    ``depends`` carries the values of the sibling fields a source declares in
    ``InputField.depends_on`` — the selected provider for ``llm.models``, say.
    It lives on the context rather than in every resolver signature so a
    resolver that does not care needs no change, and so the cache can key on
    it without a second parameter to thread everywhere.
    """

    user_id: str
    access_token: str | None = None
    depends: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionItem:
    """One resolved dropdown option."""

    value: str
    label: str
    description: str | None = None
    disabled: bool = False


@dataclass(frozen=True)
class ResolvedOptions:
    """The result of resolving one source: its options, or unavailability."""

    source: str
    items: list[OptionItem] = field(default_factory=list)
    available: bool = True


_cache: dict[tuple[str, str, str], tuple[float, list[OptionItem]]] = {}


def _depends_key(depends: dict[str, str] | None) -> str:
    """A stable cache-key fragment for a dependency set.

    Without this in the key, resolving ``llm.models`` for provider A warms a
    cache that then serves A's models to provider B — a bug that looks like a
    filtering failure and is invisible in a single-provider test.
    """
    if not depends:
        return ""
    return "&".join(f"{k}={depends[k]}" for k in sorted(depends))


def _cache_get(source: str, user_id: str, depends_key: str = "") -> list[OptionItem] | None:
    entry = _cache.get((source, user_id, depends_key))
    if entry is None:
        return None
    stored_at, items = entry
    if time.monotonic() - stored_at > _CACHE_TTL_SECONDS:
        return None
    return items


def _cache_set(source: str, user_id: str, items: list[OptionItem], depends_key: str = "") -> None:
    _cache[(source, user_id, depends_key)] = (time.monotonic(), items)


def clear_cache() -> None:
    """Test-only: reset the process-wide cache between test runs."""
    _cache.clear()


async def _http_get_json(url: str, *, access_token: str | None) -> Any:
    """The transport boundary for rag-service / Ollama calls."""
    import httpx

    headers: dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    async with httpx.AsyncClient(timeout=_RESOLVER_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def _list_rag_collection_rows() -> list[Any]:
    """Read ``(uuid, name, cmetadata)`` for every RAG collection, newest name order.

    The DB fallback for the collection dropdowns — shared by the plain and
    graph collection resolvers so the ad-hoc repository subclass lives in one
    place. Returns ``[]`` on any error; callers degrade to an empty dropdown.
    """
    try:
        from service.persistence_gateway import list_rag_collection_rows

        return await list_rag_collection_rows()
    except Exception:
        logger.warning("RAG collection DB fallback failed", exc_info=True)
        return []


def _collection_label(row: Any) -> str:
    """Prefer the human name in ``cmetadata`` over the raw collection name."""
    meta_name = row.cmetadata.get("name") if isinstance(row.cmetadata, dict) else None
    return meta_name or row.name


# ---------------------------------------------------------------------------
# LLM providers / models
# ---------------------------------------------------------------------------


async def _resolve_llm_providers(
    context: ResolverContext, *, service: Any = None
) -> list[OptionItem]:
    from domain.providers.repository import ProviderRepository
    from domain.providers.service import ProviderService

    svc = service or ProviderService(ProviderRepository())
    data = await svc.list_all(context.user_id)
    items: list[OptionItem] = []
    seen: set[str] = set()

    for row in data.get("builtin", []):
        vid = str(row["id"])
        ptype = str(row.get("provider_type") or row["id"])
        name = str(row.get("name", row["id"]))
        if vid not in seen:
            seen.add(vid)
            items.append(OptionItem(value=vid, label=name, description=ptype))

    for row in data.get("url_providers", []):
        vid = str(row["id"])
        ptype = str(row.get("provider_type") or "vllm")
        name = str(row.get("name", str(row["id"])))
        if vid not in seen:
            seen.add(vid)
            items.append(OptionItem(value=vid, label=name, description=ptype))

    for row in data.get("user_providers", []):
        vid = str(row["id"])
        ptype = str(row.get("provider_type") or "openai")
        name = str(row.get("name", str(row["id"])))
        if vid not in seen:
            seen.add(vid)
            items.append(OptionItem(value=vid, label=name, description=ptype))

    return items


def _emit_model_options(
    configs: list[Any],
    *,
    dedup_prefix: str,
    description: str,
    seen: set[str],
    items: list[OptionItem],
) -> None:
    """Append one dropdown option per non-embedding model config, deduped.

    Shared by the live-provider pass and the well-known fallback pass of
    :func:`_resolve_llm_models` so the two never drift.
    """
    from core.utils.model_classifier import is_embedding_model

    for model in configs:
        if is_embedding_model(model):
            continue
        m_name = model.get("name")
        if not m_name:
            continue
        dedup_key = f"{dedup_prefix}:{m_name}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        items.append(
            OptionItem(
                value=m_name, label=model.get("display_name") or m_name, description=description
            )
        )


async def _resolve_llm_models(context: ResolverContext, *, service: Any = None) -> list[OptionItem]:
    from domain.providers.repository import ProviderRepository
    from domain.providers.service import _WELL_KNOWN_BY_TYPE, ProviderService

    svc = service or ProviderService(ProviderRepository())
    providers = await svc.get_available_models_for_user(context.user_id)
    items: list[OptionItem] = []
    seen: set[str] = set()

    # The chosen provider, declared by LLMModel.model's depends_on. Matching is
    # exact against the provider's id or type — never a substring, which is how
    # the old client-side filter let "openai" also match "openai-compatible".
    chosen = str(context.depends.get("provider", "") or "").strip().lower()
    if chosen:
        providers = [
            p
            for p in providers
            if chosen
            in {
                str(p.get("id") or "").lower(),
                str(p.get("provider") or "").lower(),
                str(p.get("provider_type") or "").lower(),
            }
        ]

    for prov in providers:
        p_id = str(prov.get("id") or "")
        p_name = str(
            prov.get("provider_display_name") or prov.get("name") or prov.get("provider") or ""
        )
        ptype = str(prov.get("provider") or prov.get("provider_type") or "")
        configs = prov.get("model_configurations") or []
        if not configs and ptype in _WELL_KNOWN_BY_TYPE:
            configs = _WELL_KNOWN_BY_TYPE[ptype].get("known_models", [])
        _emit_model_options(
            configs,
            dedup_prefix=p_id,
            description=f"{p_id}|{ptype}|{p_name}",
            seen=seen,
            items=items,
        )

    # The well-known fallback is for "this user has no providers configured
    # yet", not for "the chosen provider has no models". Falling back with a
    # provider selected would re-offer every other provider's models, which is
    # the behaviour this change exists to remove.
    if not items and not chosen:
        for ptype, pdata in _WELL_KNOWN_BY_TYPE.items():
            p_name = str(pdata.get("name", ptype))
            _emit_model_options(
                pdata.get("known_models", []),
                dedup_prefix=ptype,
                description=f"{ptype}|{ptype}|{p_name}",
                seen=seen,
                items=items,
            )

    return items


async def _resolve_ollama_models(context: ResolverContext) -> list[OptionItem]:
    from core.utils.model_classifier import is_embedding_model
    from domain.ollama.repository import OllamaRepository
    from domain.ollama.service import OllamaService

    svc = OllamaService(OllamaRepository())
    models = await svc.list_models()
    return [
        OptionItem(value=m["name"], label=m.get("display_name") or m["name"])
        for m in models
        if not is_embedding_model(m)
    ]


# ---------------------------------------------------------------------------
# RAG / Graph RAG
# ---------------------------------------------------------------------------


async def _resolve_rag_collections(context: ResolverContext) -> list[OptionItem]:
    try:
        data = await _http_get_json(rag_url("/collections"), access_token=context.access_token)
        rows = data.get("collections", []) if isinstance(data, dict) else data
        if rows:
            return [OptionItem(value=str(r["id"]), label=r.get("name", str(r["id"]))) for r in rows]
    except Exception:
        logger.warning("rag-service /collections unavailable — falling back to DB", exc_info=True)

    return [
        OptionItem(value=str(row.uuid), label=_collection_label(row))
        for row in await _list_rag_collection_rows()
        if row.name != _DEFAULT_COLLECTION_NAME
    ]


async def _resolve_rag_graph_collections(context: ResolverContext) -> list[OptionItem]:
    name_map: dict[str, str] = {}
    for row in await _list_rag_collection_rows():
        if row.name != _DEFAULT_COLLECTION_NAME:
            label = _collection_label(row)
            name_map[str(row.uuid)] = label
            name_map[str(row.name)] = label

    try:
        data = await _http_get_json(
            rag_url("/graph/collections"), access_token=context.access_token
        )
        if isinstance(data, dict) and "collections" in data:
            cols = data["collections"]
            if isinstance(cols, list) and cols:
                return [
                    OptionItem(
                        value=str(c.get("id", c)),
                        label=c.get("name")
                        or name_map.get(str(c.get("id", c)), str(c.get("id", c))),
                    )
                    for c in cols
                ]
        ids = data.get("collection_ids", data) if isinstance(data, dict) else data
        if ids and isinstance(ids, list) and ids:
            return [
                OptionItem(
                    value=str(cid),
                    label=name_map.get(str(cid), str(cid)),
                )
                for cid in ids
            ]
    except Exception:
        pass

    if name_map:
        return [
            OptionItem(value=val, label=name)
            for val, name in name_map.items()
            if len(val) == _UUID_STRING_LENGTH and "-" in val
        ]
    return []


async def _resolve_rag_knowledge_selector(context: ResolverContext) -> list[OptionItem]:
    try:
        data = await _http_get_json(
            rag_url("/datasources/knowledge-selector"),
            access_token=context.access_token,
        )
        items: list[OptionItem] = []
        for key in ("document_processing", "knowledge_graph"):
            for row in data.get(key, []):
                items.append(
                    OptionItem(
                        value=str(row["id"]), label=row.get("name", str(row["id"])), description=key
                    )
                )
        if items:
            return items
    except Exception:
        pass

    try:
        collections = await _resolve_rag_collections(context)
        return [
            OptionItem(value=c.value, label=c.label, description="document_processing")
            for c in collections
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# MCP tools / providers
# ---------------------------------------------------------------------------


# The built-in category tool lists (offline fallback, used when the live
# MCPToolService cache is unreachable) and the canonical category list both
# come from ``domain/flows/mcp_catalog``. Adding a category is a one-line
# change there, not four edits scattered across this package.
_BUILTIN_CATEGORY_TOOLS: dict[str, list[OptionItem]] = {
    category.key: [
        OptionItem(value=tool.value, label=tool.label, description=tool.description)
        for tool in category.tools
    ]
    for category in MCP_CATEGORIES
}


async def _resolve_mcp_tools_by_category(
    context: ResolverContext, *, service: Any = None
) -> list[OptionItem]:
    try:
        from service.MCPToolService import MCPToolService

        svc = service or MCPToolService.get_instance()
        items: list[OptionItem] = []
        categories = await svc.list_categories()
        if categories:
            for category in categories:
                for tool in await svc.get_tools_by_category(category):
                    items.append(
                        OptionItem(
                            value=tool["name"],
                            label=tool.get("display_name", tool["name"]),
                            description=category,
                        )
                    )
            if items:
                return items
    except Exception:
        pass

    items = []
    for cat, cat_items in _BUILTIN_CATEGORY_TOOLS.items():
        for item in cat_items:
            items.append(
                OptionItem(
                    value=item.value,
                    label=item.label,
                    description=cat,
                )
            )
    return items


async def _resolve_mcp_category_tools(
    category: str, context: ResolverContext, *, service: Any = None
) -> list[OptionItem]:
    try:
        from service.MCPToolService import MCPToolService

        svc = service or MCPToolService.get_instance()
        tools = await svc.get_tools_by_category(category)
        if tools:
            return [
                OptionItem(
                    value=tool["name"],
                    label=tool.get("display_name", tool["name"]),
                    description=tool.get("description"),
                )
                for tool in tools
            ]
    except Exception:
        pass

    return _BUILTIN_CATEGORY_TOOLS.get(category, [])


async def _resolve_mcp_providers(
    context: ResolverContext, *, service: Any = None
) -> list[OptionItem]:
    from service.MCPProviderService import MCPProviderService

    svc = service or MCPProviderService.get_instance()
    providers = await svc.list_providers()
    return [OptionItem(value=str(p["id"]), label=p.get("name", str(p["id"]))) for p in providers]


async def _resolve_mcp_external_tools(
    context: ResolverContext,
    *,
    provider_service: Any = None,
    tool_service: Any = None,
) -> list[OptionItem]:
    """Every synced tool of every registered *external* MCP provider.

    ``value`` is the server-scoped qualified name the runtime pool keys on
    (``<slug>__<tool>``); ``description`` is ``"<provider_id>|<tool description>"``
    so the canvas ExternalMCPServer node's multiselect can narrow the list to
    the provider picked on the same node. Tools come from the cached
    ``mcp_tool`` rows — no live server connection is opened while a sidebar
    renders.
    """
    from service.MCPProviderService import MCPProviderService
    from service.MCPToolService import MCPToolService, qualify_mcp_tool_name

    psvc = provider_service or MCPProviderService.get_instance()
    tsvc = tool_service or MCPToolService.get_instance()

    providers = await psvc.list_providers()
    items: list[OptionItem] = []
    for provider in providers:
        if provider.get("type") != "external":
            continue
        tools = await tsvc.list_tools_by_provider(str(provider["id"]), include_inactive=False)
        for tool in tools:
            raw_name = tool["name"]
            description = tool.get("description") or ""
            items.append(
                OptionItem(
                    value=qualify_mcp_tool_name(provider, raw_name),
                    label=tool.get("display_name") or raw_name,
                    description=f"{provider['id']}|{description}",
                )
            )
    return items


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------


async def _resolve_mail_configs(
    context: ResolverContext, *, service: Any = None
) -> list[OptionItem]:
    from service.MailConfigService import MailConfigService

    svc = service or MailConfigService.get_instance()
    configs = await svc.list_configs(context.user_id)
    return [
        OptionItem(value=str(c["id"]), label=c.get("name", str(c["id"])))
        for c in configs
        if c.get("is_active", True)
    ]


# ---------------------------------------------------------------------------
# Agent composition
# ---------------------------------------------------------------------------


def _flow_definition_repository():
    """Indirection so a test can substitute a repository without a database."""
    from service.persistence_gateway import agent_definition_repository

    return agent_definition_repository()


async def _resolve_published_flows(
    context: ResolverContext, *, persona_repo: Any = None
) -> list[OptionItem]:
    """Flow-backed definitions that have a published spec — Run Flow's targets.

    Deliberately narrower than ``agents.definitions``, which also lists
    classic agents: only a flow can be a Run Flow target, and only a
    *published* one can be compiled. ``agent_definitions.flow_spec`` is the
    denormalized cache of the published version, so a non-null value is
    exactly "has a published version".

    A persona-linked definition's ``name`` is only an internal placeholder
    (e.g. "persona-50"); mirror ``_resolve_agent_definitions`` and prefer the
    linked persona's real display name, falling back to ``d.name``.
    """
    from service.persistence_gateway import persona_repository

    repository = _flow_definition_repository()
    definitions = await repository.list_all(graph_schema="flow")

    persona_names: dict[int, str] = {}
    try:
        p_repo = persona_repo or persona_repository()
        persona_names = {p["id"]: p["name"] for p in await p_repo.list_all()}
    except Exception:
        pass  # display-name enrichment is best-effort; fall back to d.name below

    return [
        OptionItem(
            value=str(d.id),
            label=persona_names.get(pid, str(d.name))
            if (pid := getattr(d, "persona_id", None))
            else str(d.name),
        )
        for d in definitions
        if str(getattr(d, "graph_schema", "")) == "flow" and getattr(d, "flow_spec", None)
    ]


async def _resolve_agent_definitions(
    context: ResolverContext, *, service: Any = None, persona_repo: Any = None
) -> list[OptionItem]:
    from domain.agents.service import AgentDefinitionService, build_agent_preview_text
    from service.persistence_gateway import agent_definition_repository, persona_repository

    svc = service or AgentDefinitionService(agent_definition_repository())
    definitions = await svc.list_agent_definitions(active_only=True)

    persona_names: dict[int, str] = {}
    try:
        p_repo = persona_repo or persona_repository()
        persona_names = {p["id"]: p["name"] for p in await p_repo.list_all()}
    except Exception:
        pass  # display-name enrichment is best-effort; fall back to d.name below

    return [
        OptionItem(
            value=str(d.id),
            label=persona_names.get(pid, d.name)
            if (pid := getattr(d, "persona_id", None))
            else d.name,
            description=build_agent_preview_text(d),
        )
        for d in definitions
        # design spec 5.4 — flows are not composable sub-agents
        if d.graph_schema != GraphSchemaType.FLOW
    ]


async def is_flow_backed(agent_id: str, *, repo: Any = None) -> bool:
    """Whether ``agent_id`` refers to a flow-backed agent definition.

    Async because it is a DB lookup. Task 3's validator calls a plain,
    synchronous callback — Task 6's route layer must resolve this for every
    ``agent_id`` referenced in a flow *before* calling ``validate()``, then
    pass a closure over the resolved results.
    """
    from service.persistence_gateway import agent_definition_repository

    repository = repo or agent_definition_repository()
    try:
        definition_id = UUID(agent_id)
    except (ValueError, TypeError, AttributeError):
        return False
    definition = await repository.get_by_id(definition_id)
    return definition is not None and definition.graph_schema == GraphSchemaType.FLOW


# ---------------------------------------------------------------------------
# Datasources / web search
# ---------------------------------------------------------------------------


async def _resolve_datasources(
    context: ResolverContext, *, controller: Any = None
) -> list[OptionItem]:
    from controller import get_data_controller

    ctrl = controller or get_data_controller()
    rows = await ctrl.list_datasources()
    return [OptionItem(value=str(r["id"]), label=r.get("name", str(r["id"]))) for r in rows]


async def _resolve_websearch_providers(
    context: ResolverContext, *, controller: Any = None
) -> list[OptionItem]:
    from controller import get_web_search_controller

    ctrl = controller or get_web_search_controller()
    rows = ctrl.list_search_providers()  # sync
    return [OptionItem(value=str(r["id"]), label=r.get("name", str(r["id"]))) for r in rows]


async def _resolve_websearch_content_providers(
    context: ResolverContext, *, controller: Any = None
) -> list[OptionItem]:
    from controller import get_web_search_controller

    ctrl = controller or get_web_search_controller()
    rows = ctrl.list_content_providers()  # sync
    return [
        OptionItem(
            value=str(r.get("provider_type") or r.get("id")),
            label=r.get("name", str(r.get("id"))),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Canonical list lives in ``domain/flows/mcp_catalog``; kept as a module
# alias so the dispatch table below reads the same as before.
_MCP_CATEGORIES = MCP_CATEGORY_KEYS


def _make_category_resolver(cat: str) -> Callable[[ResolverContext], Awaitable[list[OptionItem]]]:
    async def _resolve(context: ResolverContext) -> list[OptionItem]:
        return await _resolve_mcp_category_tools(cat, context)

    return _resolve


_RESOLVERS: dict[str, Callable[[ResolverContext], Awaitable[list[OptionItem]]]] = {
    "llm.providers": _resolve_llm_providers,
    "llm.models": _resolve_llm_models,
    "ollama.models": _resolve_ollama_models,
    "rag.collections": _resolve_rag_collections,
    "rag.graph_collections": _resolve_rag_graph_collections,
    "rag.knowledge_selector": _resolve_rag_knowledge_selector,
    "mcp.tools_by_category": _resolve_mcp_tools_by_category,
    "mcp.providers": _resolve_mcp_providers,
    "mcp.external_tools": _resolve_mcp_external_tools,
    "mail.configs": _resolve_mail_configs,
    "agents.definitions": _resolve_agent_definitions,
    "flows.published": _resolve_published_flows,
    "datasources.list": _resolve_datasources,
    "websearch.providers": _resolve_websearch_providers,
    "websearch.content_providers": _resolve_websearch_content_providers,
    **{f"mcp.tools.{cat}": _make_category_resolver(cat) for cat in _MCP_CATEGORIES},
}


async def resolve_options(source: str, context: ResolverContext) -> ResolvedOptions:
    """Resolve one ``options_source`` key for the calling user.

    Cached 30s per ``(source, user_id)``. An unreachable upstream never
    raises — it degrades to an empty, ``available=False`` result so the rest
    of the sidebar keeps working.
    """
    if source not in KNOWN_OPTIONS_SOURCES:
        raise UnknownOptionsSourceError(source)

    depends_key = _depends_key(context.depends)
    cached = _cache_get(source, context.user_id, depends_key)
    if cached is not None:
        return ResolvedOptions(source=source, items=cached, available=True)

    resolver = _RESOLVERS[source]
    try:
        items = await resolver(context)
    except Exception:
        return ResolvedOptions(source=source, items=[], available=False)

    _cache_set(source, context.user_id, items, depends_key)
    return ResolvedOptions(source=source, items=items, available=True)


async def resource_exists(source: str, value: str, context: ResolverContext) -> bool:
    """Whether ``value`` is among the currently resolvable options for ``source``.

    Used by Task 6's save/publish path for ``FLOW_UNKNOWN_RESOURCE`` — a flow
    referencing a collection, tool, or agent that no longer exists or isn't
    visible to the caller. If the upstream is unreachable, this returns
    ``True`` (does not block a save on a transient failure elsewhere).
    """
    resolved = await resolve_options(source, context)
    if not resolved.available:
        return True
    return any(item.value == value for item in resolved.items)
