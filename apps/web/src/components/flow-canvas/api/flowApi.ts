/**
 * Endpoint builders for the flow-canvas HTTP surface.
 *
 * Single source of truth for the `/api/agent-definitions/{id}/flow/...` and
 * `/api/flow-components/...` paths, which were hand-built (and occasionally
 * string-concatenated) in ~10 hooks and pages. Change a path here, not there.
 */

const AGENT_DEFINITIONS_BASE = "/api/agent-definitions";
const FLOW_COMPONENTS_BASE = "/api/flow-components";

const flowBase = (definitionId: string) =>
  `${AGENT_DEFINITIONS_BASE}/${definitionId}/flow`;

export const flowApi = {
  /** GET/PUT the mutable draft. */
  draft: (definitionId: string) => `${flowBase(definitionId)}/draft`,
  /** GET the currently published flow. */
  published: (definitionId: string) => `${flowBase(definitionId)}/published`,
  /** GET version history (newest first). */
  versions: (definitionId: string) => `${flowBase(definitionId)}/versions`,
  /** GET one version's metadata + spec. */
  version: (definitionId: string, versionNo: number | string) =>
    `${flowBase(definitionId)}/versions/${versionNo}`,
  /** POST: promote the draft to published. */
  publish: (definitionId: string) => `${flowBase(definitionId)}/publish`,
  /** POST: restore a previous version. */
  rollback: (definitionId: string) => `${flowBase(definitionId)}/rollback`,
  /** GET the flow for a named source ("draft" | "published"). */
  bySource: (definitionId: string, source: string) =>
    `${flowBase(definitionId)}/${source}`,
  /** POST: validate a flow spec without persisting. */
  validate: () => `${AGENT_DEFINITIONS_BASE}/validate-flow`,
  /** SSE: playground run stream (definition-scoped, or unscoped for ad-hoc specs). */
  playgroundStream: (definitionId?: string) =>
    definitionId
      ? `${flowBase(definitionId)}/playground/runs/stream`
      : `${AGENT_DEFINITIONS_BASE}/flow/playground/runs/stream`,
  /** GET the grouped component registry. */
  components: () => FLOW_COMPONENTS_BASE,
  /** GET resolved options for a dynamic `options_source`. */
  componentOptions: (source: string) =>
    `${FLOW_COMPONENTS_BASE}/options/${source}`,
} as const;
