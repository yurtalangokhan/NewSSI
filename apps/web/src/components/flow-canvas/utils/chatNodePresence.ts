/**
 * Which chat entry/exit nodes a flow currently holds.
 *
 * A flow-backed agent needs a `ChatInput` and a `ChatOutput` node to be
 * publishable — the backend enforces this in `domain/flows/validator.py`
 * (`FLOW_NO_ENTRY` / `FLOW_NO_EXIT`). This helper is the single client-side
 * definition of "which node type is the chat entry / exit", shared by the
 * inline designer's Playground gate and the create page's submit gate so
 * the two never drift apart.
 */

export const CHAT_INPUT_COMPONENT = "ChatInput";
export const CHAT_OUTPUT_COMPONENT = "ChatOutput";

type NodeLike = { data?: { type?: string } | undefined };

export interface ChatNodePresence {
  hasChatInput: boolean;
  hasChatOutput: boolean;
}

export function getChatNodePresence(
  nodes: ReadonlyArray<NodeLike>
): ChatNodePresence {
  let hasChatInput = false;
  let hasChatOutput = false;
  for (const node of nodes) {
    const type = node.data?.type;
    if (type === CHAT_INPUT_COMPONENT) hasChatInput = true;
    else if (type === CHAT_OUTPUT_COMPONENT) hasChatOutput = true;
  }
  return { hasChatInput, hasChatOutput };
}

/** True when the flow has both a chat entry and a chat exit node — the
 * minimum structural shape the backend will accept on publish. */
export function hasRequiredChatNodes(nodes: ReadonlyArray<NodeLike>): boolean {
  const { hasChatInput, hasChatOutput } = getChatNodePresence(nodes);
  return hasChatInput && hasChatOutput;
}
