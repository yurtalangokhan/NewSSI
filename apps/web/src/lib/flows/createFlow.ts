import { createPersona } from "@/app/admin/agents/lib";
import { flowApi } from "@/components/flow-canvas/api/flowApi";
import { buildSeedFlowSpec } from "@/lib/flows/seedFlow";

export type FlowMetadataInput = {
  name: string;
  description: string;
  uploadedImageId: string | null;
  iconName: string | null;
  starterMessages: string[];
  isPublic: boolean;
  featured: boolean;
  /** Selections made in the share dialog before the flow exists — sent
   * with the create call so a flow can be shared at creation time, just
   * like an agent. */
  sharedUserIds?: string[];
  sharedGroupIds?: number[];
  labelIds?: number[];
};

export type CreatedFlow = { personaId: number; definitionId: string };

export class FlowCreationError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Create the persona + definition behind a flow and seed its draft.
 *
 * The persona is written first because the definition id — which every
 * flow endpoint keys on — only exists once the backend has created it.
 * A failure after that point leaves a real, editable flow rather than a
 * phantom: the caller surfaces the error and the user can open or delete
 * it from the list.
 */
export async function createFlow(
  input: FlowMetadataInput
): Promise<CreatedFlow> {
  const response = await createPersona({
    name: input.name,
    description: input.description,
    system_prompt: "",
    replace_base_system_prompt: false,
    task_prompt: "",
    datetime_aware: true,
    document_set_ids: [],
    is_public: input.isPublic,
    llm_model_provider_override: null,
    llm_model_version_override: null,
    starter_messages: input.starterMessages
      .filter((message) => message.trim().length > 0)
      .map((message) => ({ name: message, message })),
    users: input.sharedUserIds ?? [],
    groups: input.sharedGroupIds ?? [],
    tool_ids: [],
    search_start_date: null,
    uploaded_image_id: input.uploadedImageId,
    icon_name: input.iconName,
    featured: input.featured,
    label_ids: input.labelIds ?? null,
    user_file_ids: [],
    base_agent: "dynamic-agent",
    graph_schema: "flow",
    brain_type: "llm",
    memory_type: "none",
  });

  if (!response) {
    throw new FlowCreationError("Flow creation failed: no response", 500);
  }

  if (!response.ok) {
    throw new FlowCreationError(
      `Flow creation failed: ${response.status}`,
      response.status
    );
  }

  const persona = await response.json();
  let definitionId: string | undefined = persona.agent_definition_id;

  if (!definitionId) {
    // The catalog merges this id in; a create response that omits it means
    // the definition row exists but wasn't serialized — read it back.
    const detail = await fetch(`/api/agents/${persona.id}`, {
      credentials: "include",
    });
    const merged = await detail.json();
    definitionId = merged.agent_definition_id;
    if (!definitionId) {
      throw new FlowCreationError(
        "Flow was created without a definition id",
        500
      );
    }
  }

  await fetch(flowApi.draft(definitionId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ flow_spec: buildSeedFlowSpec() }),
  });

  return { personaId: persona.id, definitionId };
}
