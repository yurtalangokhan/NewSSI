import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { getErrorMsg } from "@/lib/fetchUtils";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError, parseApiErrorResponse } from "@/lib/api/http/errors";

import { AgentId } from "@/lib/api/domains/agents/endpoints";
import "@/lib/api/domains/access/endpoints";

import { parseResponseModel } from "@/lib/api/responseModel";

import type {
  AgentFlowPlaygroundRunPayload,
  AgentFlowSpec,
} from "@/lib/api/domains/agents/types";

// ============================================================================
// Helpers
// ============================================================================

async function fetchAgentSWRJson<T>(path: string, wrapped = false): Promise<T> {
  const response = await apiRequest(path, {
    headers: { "X-Language": i18n.language },
  });
  if (!response.ok) {
    const parsedError = await parseApiErrorResponse(response);
    throw new FetchError(
      parsedError.userMessage,
      response.status,
      parsedError.raw,
      parsedError
    );
  }
  if (wrapped) return parseResponseModel<T>(response);
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return {} as T;
  }
  return payload as T;
}

export const fetchAgentGraphSchemas = <T>() =>
  fetchAgentSWRJson<T>(agentsEndpoints.agentGraphSchemas.browserPath, true);
export const fetchAgentBrains = <T>() =>
  fetchAgentSWRJson<T>(agentsEndpoints.agentBrains.browserPath, true);
export const fetchAgentMemoryTypes = <T>() =>
  fetchAgentSWRJson<T>(agentsEndpoints.agentMemoryTypes.browserPath, true);
export const fetchComponentTemplates = <T>() =>
  fetchAgentSWRJson<T>(agentsEndpoints.flowComponentCatalog.browserPath, true);
export const fetchResolvedComponentOptions = <T>(
  source: string,
  depends: Record<string, string> = {}
) =>
  fetchAgentSWRJson<T>(
    agentsEndpoints.resolvedOptions(source, depends).browserPath,
    true
  );
export const fetchFlowVersions = <T>(definitionId: string) =>
  fetchAgentSWRJson<T>(
    agentsEndpoints.flowVersions(definitionId).browserPath,
    true
  );
export const fetchFlowSource = <T>(
  definitionId: string,
  source: "draft" | "published" | number
) =>
  fetchAgentSWRJson<T>(
    typeof source === "number"
      ? agentsEndpoints.flowVersion(definitionId, source).browserPath
      : agentsEndpoints.flowBySource(definitionId, source).browserPath,
    true
  );
export const fetchPersonaLabelsForSWR = <T>() =>
  fetchAgentSWRJson<T>(agentsEndpoints.personaLabels.browserPath, true);

// ============================================================================
// Types
// ============================================================================

// ============================================================================
// Catalog and detail (user-facing)
// ============================================================================

export function fetchAgentCatalog<T = unknown[]>(): Promise<T> {
  return fetchAgentSWRJson<T>(agentsEndpoints.agentCatalog().browserPath, true);
}

export function fetchAgentDetail<T = unknown>(agentId: AgentId): Promise<T> {
  return fetchAgentSWRJson<T>(
    agentsEndpoints.getAgent(agentId).browserPath,
    true
  );
}

export function fetchCompositionCatalog<T = unknown>(): Promise<T> {
  return fetchAgentSWRJson<T>(
    agentsEndpoints.getCompositionCatalog().browserPath,
    true
  );
}

/**
 * Fetches agents available for composition with optional filtering.
 */
export async function fetchAvailableForComposition({
  schema,
  excludeIds,
}: {
  schema?: string | null;
  excludeIds?: string[];
}): Promise<unknown[]> {
  const res = await apiRequest(
    agentsEndpoints.availableForComposition.browserPath,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        schema: schema || undefined,
        exclude_ids: excludeIds?.length ? excludeIds : undefined,
      }),
    }
  );

  if (!res.ok) {
    throw new Error(`Failed to fetch available agents: ${res.statusText}`);
  }

  return parseResponseModel<unknown[]>(res);
}

// ============================================================================
// User agent operations
// ============================================================================

/**
 * Updates the user's pinned assistants with the given ordered list of agent IDs.
 */

/**
 * Deletes an agent by its ID.
 */
export async function deleteAgent(agentId: AgentId): Promise<string | null> {
  try {
    const endpoint = agentsEndpoints.agentDelete(agentId).browserPath;
    const response = await apiRequest(endpoint, {
      method: "DELETE",
    }).then(agentServicePayloadResponse);

    if (response.ok) {
      return null;
    }

    const errorMessage = (await getErrorMsg(response)) || "Unknown error";
    return errorMessage;
  } catch (error) {
    console.error("deleteAgent: Network error", error);
    return "Network error. Please check your connection and try again.";
  }
}

/**
 * Updates agent sharing settings.
 */
export async function updateAgentSharedStatus(
  agentId: number,
  userIds: string[],
  groupIds: number[],
  isPublic: boolean | undefined,
  isPaidEnterpriseFeaturesEnabled: boolean,
  labelIds?: number[]
): Promise<null | string> {
  // MIT versions should not send group_ids - warn if caller provided non-empty groups
  if (!isPaidEnterpriseFeaturesEnabled && groupIds.length > 0) {
    console.error(
      "updateAgentSharedStatus: groupIds provided but enterprise features are disabled. " +
        "Group sharing is an EE-only feature. Discarding groupIds."
    );
  }

  try {
    const response = await apiRequest(
      agentsEndpoints.agentShare(agentId).browserPath,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_ids: userIds,
          // Only include group_ids for enterprise versions
          group_ids: isPaidEnterpriseFeaturesEnabled ? groupIds : undefined,
          is_public: isPublic,
          label_ids: labelIds,
        }),
      }
    ).then(agentServicePayloadResponse);

    if (response.ok) {
      return null;
    }

    const errorMessage = (await getErrorMsg(response)) || "Unknown error";
    return errorMessage;
  } catch (error) {
    console.error("updateAgentSharedStatus: Network error", error);
    return "Network error. Please check your connection and try again.";
  }
}

/**
 * Updates the labels assigned to an agent via the share endpoint.
 */

/**
 * Updates the featured (default) status of an agent.
 */
export async function updateAgentFeaturedStatus(
  agentId: number,
  isFeatured: boolean
): Promise<string | null> {
  try {
    const response = await apiRequest(
      agentsEndpoints.personaFeatured(agentId).browserPath,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ featured: isFeatured }),
      }
    ).then(agentServicePayloadResponse);

    if (response.ok) {
      return null;
    }

    const errorMessage = (await getErrorMsg(response)) || "Unknown error";
    return errorMessage;
  } catch (error) {
    console.error("updateAgentFeaturedStatus: Network error", error);
    return "Network error. Please check your connection and try again.";
  }
}

// ============================================================================
// Admin persona/label operations
// ============================================================================

export function togglePersonaFeatured(
  personaId: string | number,
  featured: boolean
): Promise<Response> {
  return apiRequest(agentsEndpoints.personaFeatured(personaId).browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ featured: !featured }),
    credentials: "include",
  });
}

export function togglePersonaVisibility(
  personaId: string | number,
  visible: boolean
): Promise<Response> {
  return apiRequest(agentsEndpoints.personaVisible(personaId).browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_visible: !visible }),
    credentials: "include",
  });
}

// ============================================================================
// Admin standard answer operations
// ============================================================================

export function createStandardAnswer(data: unknown): Promise<Response> {
  return apiRequest(agentsEndpoints.standardAnswer.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function updateStandardAnswer(
  answerId: string | number,
  data: unknown
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.standardAnswerDetail(String(answerId)).browserPath,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }
  );
}

export function deleteStandardAnswer(
  answerId: string | number
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.standardAnswerDetail(String(answerId)).browserPath,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    }
  );
}

export function createStandardAnswerCategory(data: unknown): Promise<Response> {
  return apiRequest(agentsEndpoints.standardAnswerCategory.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ============================================================================
// Persona options and admin personas
// ============================================================================

export interface PersonaOption {
  id: number;
  name: string;
  description: string;
}

export function fetchPersonaOptions(): Promise<PersonaOption[]> {
  return fetchAgentSWRJson<PersonaOption[]>(
    agentsEndpoints.personaOptions.browserPath,
    true
  );
}

export function fetchAdminPersonas<T = unknown>(params?: {
  include_deleted?: boolean;
  get_editable?: boolean;
  include_default?: boolean;
  page_num?: number;
  page_size?: number;
}): Promise<T> {
  return fetchAgentSWRJson<T>(
    agentsEndpoints.adminPersonas(params).browserPath
  );
}

export function fetchPersonas<T = unknown>(params?: {
  include_deleted?: boolean;
  get_editable?: boolean;
}): Promise<T> {
  return fetchAgentSWRJson<T>(
    agentsEndpoints.personas(params).browserPath,
    true
  );
}

import {
  PersonaUpsertParameters,
  buildPersonaUpsertRequest,
} from "@/lib/api/domains/agents/requests";
import i18n from "@/i18n/config";

export async function createPersona(
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  const createPersonaResponse = await apiRequest(
    agentsEndpoints.createPersona.browserPath,
    {
      method: agentsEndpoints.createPersona.method,
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildPersonaUpsertRequest(personaUpsertParams)),
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);

  return createPersonaResponse;
}

export async function updatePersona(
  id: number,
  personaUpsertParams: PersonaUpsertParameters
): Promise<Response | null> {
  const updatePersonaResponse = await apiRequest(
    agentsEndpoints.updateNumericPersona(id).browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildPersonaUpsertRequest(personaUpsertParams)),
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);

  return updatePersonaResponse;
}

export function deletePersona(personaId: number) {
  return apiRequest(
    agentsEndpoints.deleteNumericPersona(personaId).browserPath,
    {
      method: "DELETE",
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);
}

export function updatePersonaDisplayPriorities(payload: {
  display_priority_map: { [k: string]: number };
}): Promise<Response> {
  return apiRequest(
    agentsEndpoints.updatePersonaDisplayPriorities.browserPath,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );
}

export function requestAgentFlowExpansion(agentId: string): Promise<Response> {
  return apiRequest(
    agentsEndpoints.requestAgentFlowExpansion(agentId).browserPath,
    {
      method: "POST",
    }
  );
}

export function validateAgentCompositionResponse(payload: {
  agent_id: string | null;
  graph_schema: string;
  sub_agent_ids: string[];
}): Promise<Response> {
  return apiRequest(agentsEndpoints.validateAgentComposition.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function uploadAgentIcon(body: FormData): Promise<Response> {
  return apiRequest(agentsEndpoints.uploadPersonaImage.browserPath, {
    method: "POST",
    body: body,
  }).then(agentServicePayloadResponse);
}

export function loadMutableFlowDraft(definitionId: string): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadMutableFlowDraft(definitionId).browserPath,
    {
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);
}

export function loadPublishedFlowSeed(definitionId: string): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadPublishedFlowSeed(definitionId).browserPath,
    {
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);
}

export function saveMutableFlowDraft(
  definitionId: string,
  payload: { flow_spec: AgentFlowSpec }
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadMutableFlowDraft(definitionId).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function discardMutableFlowDraft(
  definitionId: string
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadMutableFlowDraft(definitionId).browserPath,
    {
      method: "DELETE",
      credentials: "include",
    }
  ).then(agentServicePayloadResponse);
}

export function validateCanvasFlow(payload: {
  flow_spec: AgentFlowSpec;
}): Promise<Response> {
  return apiRequest(agentsEndpoints.validateCanvasFlow.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function publishCanvasFlow(
  definitionId: string,
  payload: Record<string, unknown>
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.publishCanvasFlow(definitionId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function rollbackCanvasFlow(
  definitionId: string,
  payload: { target_version_no: number }
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.rollbackCanvasFlow(definitionId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function fetchCanvasFlowVersion(
  definitionId: string,
  versionNo: number
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.fetchCanvasFlowVersion(definitionId, versionNo).browserPath,
    { credentials: "include" }
  ).then(agentServicePayloadResponse);
}

export function createPersonaLabel(payload: {
  name: string;
}): Promise<Response> {
  return apiRequest(agentsEndpoints.personaLabels.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updatePersonaLabel(
  id: number,
  payload: { label_name: string }
): Promise<Response> {
  return apiRequest(agentsEndpoints.updatePersonaLabel(id).browserPath, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deletePersonaLabel(id: number): Promise<Response> {
  return apiRequest(agentsEndpoints.updatePersonaLabel(id).browserPath, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
  });
}

export function saveEditorInitialFlow(
  definitionId: string,
  payload: { flow_spec: unknown }
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadMutableFlowDraft(definitionId).browserPath,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function publishEditorInitialFlow(
  definitionId: string,
  payload: {}
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.publishCanvasFlow(definitionId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function validateEditorInlineFlow(payload: {
  flow_spec: unknown;
}): Promise<Response> {
  return apiRequest(agentsEndpoints.validateEditorInlineFlow.browserPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}

export function saveEditorConvertedFlow(
  definitionId: string,
  payload: { nodes: never[]; edges: never[] }
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.loadMutableFlowDraft(definitionId).browserPath,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  ).then(agentServicePayloadResponse);
}

export function streamFlowPlaygroundRun(
  definitionId: string | undefined,
  payload: AgentFlowPlaygroundRunPayload,
  signal?: AbortSignal
): Promise<Response> {
  return apiRequest(
    agentsEndpoints.streamFlowPlaygroundRun(definitionId).browserPath,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }
  );
}

export function createDynamicDefinitionResponse(
  payload: Record<string, unknown>
): Promise<Response> {
  return apiRequest(agentsEndpoints.agentDefinitionsBase.browserPath, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(agentServicePayloadResponse);
}
