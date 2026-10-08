export type AgentId = number | string;

/** Backend mapping for the existing /api/agent and LangGraph catch-all routes. */

// ============================================================================
// Catalog and detail endpoints
// ============================================================================

// ============================================================================
// Admin persona/label endpoints
// ============================================================================

export interface AdminPersonasPathParams {
  include_deleted?: boolean;
  get_editable?: boolean;
  include_default?: boolean;
  page_num?: number;
  page_size?: number;
}

export interface PersonasPathParams {
  include_deleted?: boolean;
  get_editable?: boolean;
}

// ============================================================================
// Admin standard answer endpoints
// ============================================================================

// ============================================================================
// User agent operations
// ============================================================================

/**
 * Endpoint builders for the flow-canvas HTTP surface.
 *
 * Single source of truth for the `/api/agent-definitions/{id}/flow/...` and
 * `/api/flow-components/...` paths, which were hand-built (and occasionally
 * string-concatenated) in ~10 hooks and pages. Change a path here, not there.
 */

export const agentsEndpoints = {
  proxyResourceTarget: (segments: string[]) =>
    ({
      backend: {
        service: "agent",
        path: `/api/v1/proxy/${segments.join("/")}`,
      },
    }) as const,
  apiProxy: (segments: string[]) =>
    ({
      backend: { service: "agent", path: `/api/v1/${segments.join("/")}` },
    }) as const,
  uploadPersonaImage: {
    method: "POST",
    browserPath: "/api/admin/persona/upload-image",
    backend: { service: "agent", path: "/api/v1/admin/persona/upload-image" },
  },
  getPersona: (personaId: string | number) =>
    ({
      method: "GET",
      browserPath: `/api/persona/${encodeURIComponent(String(personaId))}`,
      backend: {
        service: "agent",
        path: `/api/v1/persona/${encodeURIComponent(String(personaId))}`,
      },
    }) as const,
  updatePersona: (personaId: string | number) =>
    ({
      method: "PATCH",
      browserPath: `/api/persona/${encodeURIComponent(String(personaId))}`,
      backend: {
        service: "agent",
        path: `/api/v1/persona/${encodeURIComponent(String(personaId))}`,
      },
    }) as const,
  deletePersona: (personaId: string | number) =>
    ({
      method: "DELETE",
      browserPath: `/api/persona/${encodeURIComponent(String(personaId))}`,
      backend: {
        service: "agent",
        path: `/api/v1/persona/${encodeURIComponent(String(personaId))}`,
      },
    }) as const,
  updateNumericPersona: (id: number) =>
    ({
      method: "PATCH",
      browserPath: `/api/persona/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/persona/${encodeURIComponent(String(id))}`,
      },
    }) as const,
  deleteNumericPersona: (id: number) =>
    ({
      method: "DELETE",
      browserPath: `/api/persona/${id}`,
      backend: {
        service: "agent",
        path: `/api/v1/persona/${encodeURIComponent(String(id))}`,
      },
    }) as const,
  getAgent: (agentId: AgentId) =>
    ({
      method: "GET",
      browserPath: `/api/agents/${encodeURIComponent(String(agentId))}`,
      backend: {
        service: "agent",
        path: `/api/v1/agents/${encodeURIComponent(String(agentId))}`,
      },
    }) as const,
  listPersonas: {
    method: "GET",
    browserPath: "/api/persona",
    backend: { service: "agent", path: "/api/v1/persona" },
  },
  createPersona: {
    method: "POST",
    browserPath: "/api/persona",
    backend: { service: "agent", path: "/api/v1/persona" },
  },
  catalog: {
    method: "GET",
    browserPath: "/api/agents/catalog",
    backend: { service: "agent", path: "/api/v1/agents/catalog" },
  },
  agentProxyTarget: (
    path: string
  ): { backend: import("@/lib/api/http/types").BackendTarget } => {
    const relative = path.replace(/^\/+/, "");
    const endpoint = relative.startsWith("mcp/")
      ? `/api/v1/proxy/${relative}`
      : relative === "api/v1" || relative.startsWith("api/v1/")
        ? `/${relative}`
        : `/api/v1/${relative.replace(/^api\//, "")}`;
    return { backend: { service: "agent", path: endpoint } as const };
  },
  compositionCatalog: {
    method: "GET",
    browserPath: "/api/agents/composition/catalog",
    backend: {
      service: "agent",
      path: "/api/v1/agents/composition/catalog",
    },
  },
  availableForComposition: {
    browserPath: "/api/agent-definitions/available-for-composition",
  },
  agentCatalog: (): { browserPath: string } => {
    return { browserPath: agentsEndpoints.catalog.browserPath };
  },
  getCompositionCatalog: (): { browserPath: string } => {
    return { browserPath: agentsEndpoints.compositionCatalog.browserPath };
  },
  personaLabels: { browserPath: "/api/persona/labels" },
  personaOptions: { browserPath: "/api/persona/options" },
  adminAgents: { browserPath: "/api/admin/agents" },
  appendDefinedQuery: (
    path: string,
    params: Record<string, string | number | boolean | null | undefined>
  ): { browserPath: string } => {
    const entries = Object.entries(params)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(
        ([key, value]) =>
          `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`
      );
    return {
      browserPath: entries.length ? `${path}?${entries.join("&")}` : path,
    };
  },
  adminPersonas: (
    params: AdminPersonasPathParams = {}
  ): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.appendDefinedQuery(
        agentsEndpoints.adminAgents.browserPath,
        {
          include_deleted: params.include_deleted,
          get_editable: params.get_editable,
          include_default: params.include_default,
          page_num: params.page_num,
          page_size: params.page_size,
        }
      ).browserPath,
    };
  },
  personas: (params: PersonasPathParams = {}): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.appendDefinedQuery(
        agentsEndpoints.listPersonas.browserPath,
        {
          include_deleted: params.include_deleted,
          get_editable: params.get_editable,
        }
      ).browserPath,
    };
  },
  personaFeatured: (personaId: string | number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/persona/${encodeURIComponent(
        String(personaId)
      )}/featured`,
    };
  },
  personaVisible: (personaId: string | number): { browserPath: string } => {
    return {
      browserPath: `/api/admin/persona/${encodeURIComponent(
        String(personaId)
      )}/visible`,
    };
  },
  standardAnswer: { browserPath: "/api/manage/admin/standard-answer" },
  standardAnswerCategory: {
    browserPath: "/api/manage/admin/standard-answer/category",
  },
  standardAnswerDetail: (answerId: string): { browserPath: string } => {
    return {
      browserPath: `/api/manage/admin/standard-answer/${encodeURIComponent(
        answerId
      )}`,
    };
  },
  agentDelete: (agentId: AgentId): { browserPath: string } => {
    if (typeof agentId === "string") {
      return { browserPath: `/api/agent-definitions/${agentId}` };
    }
    return { browserPath: `/api/persona/${agentId}` };
  },
  agentShare: (agentId: AgentId): { browserPath: string } => {
    return {
      browserPath: `/api/persona/${encodeURIComponent(String(agentId))}/share`,
    };
  },
  updatePersonaDisplayPriorities: {
    browserPath: "/api/admin/agents/display-priorities",
  },
  requestAgentFlowExpansion: (agentId: string): { browserPath: string } => {
    return { browserPath: `/api/agent-definitions/${agentId}/expand` };
  },
  validateAgentComposition: {
    browserPath: "/api/agent-definitions/validate-composition",
  },
  agentDefinitionsBase: { browserPath: "/api/agent-definitions" },
  flowComponentsBase: { browserPath: "/api/flow-components" },
  flowBase: (definitionId: string): { browserPath: string } => ({
    browserPath: `${agentsEndpoints.agentDefinitionsBase.browserPath}/${definitionId}/flow`,
  }),
  flowDraft: (definitionId: string): { browserPath: string } => ({
    browserPath: `${agentsEndpoints.flowBase(definitionId).browserPath}/draft`,
  }),
  flowPublished: (definitionId: string): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/published`,
  }),
  flowVersions: (definitionId: string): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/versions`,
  }),
  flowVersion: (
    definitionId: string,
    versionNo: number | string
  ): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/versions/${versionNo}`,
  }),
  flowPublish: (definitionId: string): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/publish`,
  }),
  flowRollback: (definitionId: string): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/rollback`,
  }),
  flowBySource: (
    definitionId: string,
    source: string
  ): { browserPath: string } => ({
    browserPath: `${
      agentsEndpoints.flowBase(definitionId).browserPath
    }/${source}`,
  }),
  flowValidate: (): { browserPath: string } => ({
    browserPath: `${agentsEndpoints.agentDefinitionsBase.browserPath}/validate-flow`,
  }),
  flowPlaygroundStream: (definitionId?: string): { browserPath: string } => ({
    browserPath: definitionId
      ? `${
          agentsEndpoints.flowBase(definitionId).browserPath
        }/playground/runs/stream`
      : `${agentsEndpoints.agentDefinitionsBase.browserPath}/flow/playground/runs/stream`,
  }),
  flowComponents: (): { browserPath: string } => ({
    browserPath: agentsEndpoints.flowComponentsBase.browserPath,
  }),
  flowComponentOptions: (source: string): { browserPath: string } => ({
    browserPath: `${agentsEndpoints.flowComponentsBase.browserPath}/options/${source}`,
  }),
  loadMutableFlowDraft: (definitionId: string): { browserPath: string } => {
    return { browserPath: agentsEndpoints.flowDraft(definitionId).browserPath };
  },
  loadPublishedFlowSeed: (definitionId: string): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.flowPublished(definitionId).browserPath,
    };
  },
  validateCanvasFlow: { browserPath: "/api/agent-definitions/validate-flow" },
  publishCanvasFlow: (definitionId: string): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.flowPublish(definitionId).browserPath,
    };
  },
  rollbackCanvasFlow: (definitionId: string): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.flowRollback(definitionId).browserPath,
    };
  },
  fetchCanvasFlowVersion: (
    definitionId: string,
    versionNo: number
  ): { browserPath: string } => {
    return {
      browserPath: agentsEndpoints.flowVersion(definitionId, versionNo)
        .browserPath,
    };
  },
  updatePersonaLabel: (id: number): { browserPath: string } => {
    return { browserPath: `/api/admin/persona/label/${id}` };
  },
  validateEditorInlineFlow: {
    browserPath: "/api/agent-definitions/validate-flow",
  },
  agentGraphSchemas: { browserPath: "/api/agent-definitions/schemas/list" },
  agentBrains: { browserPath: "/api/agent-definitions/brains/list" },
  agentMemoryTypes: { browserPath: "/api/agent-definitions/memory/list" },
  flowComponentCatalog: { browserPath: "/api/flow-components" },
  definitions: (
    segments: string[] = []
  ): { backend: import("@/lib/api/http/types").BackendTarget } => ({
    backend: {
      service: "agent" as const,
      path: `/api/v1/agent-definitions${
        segments.length ? `/${segments.join("/")}` : ""
      }`,
    },
  }),
  flowComponentProxy: (
    segments: string[] = []
  ): { backend: import("@/lib/api/http/types").BackendTarget } => ({
    backend: {
      service: "agent" as const,
      path: `/api/v1/flow-components${
        segments.length ? `/${segments.join("/")}` : ""
      }`,
    },
  }),
  resolvedOptions: (
    source: string,
    depends: Record<string, string> = {}
  ): { browserPath: string } => {
    const names = Object.keys(depends).sort();
    const base = agentsEndpoints.flowComponentOptions(source).browserPath;
    if (names.length === 0) return { browserPath: base };
    const query = names
      .map((name) => `dep=${encodeURIComponent(`${name}:${depends[name]}`)}`)
      .join("&");
    return { browserPath: `${base}?${query}` };
  },
  streamFlowPlaygroundRun: (
    definitionId: string | undefined
  ): { browserPath: string } => {
    return {
      browserPath:
        agentsEndpoints.flowPlaygroundStream(definitionId).browserPath,
    };
  },
} as const;
