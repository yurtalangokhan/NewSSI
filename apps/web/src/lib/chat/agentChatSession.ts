import { DEFAULT_AGENT_ID } from "@/lib/constants";

/**
 * True for a chat bound to an agent or flow persona. A plain-model chat has
 * the default persona (0), the same rule the backend history filter applies.
 */
export function isAgentChatSession(
  session: { persona_id?: number | string | null } | null | undefined
): boolean {
  const personaId = session?.persona_id;
  if (personaId === null || personaId === undefined || personaId === "") {
    return false;
  }
  return Number(personaId) !== DEFAULT_AGENT_ID;
}

type PersonaId = number | string | null | undefined;

/**
 * Persona of the open chat. The loaded session (chat store) is authoritative
 * because it exists for any chat; the sidebar list only holds its first pages.
 */
export function resolveChatPersonaId(
  loadedPersonaId: PersonaId,
  listedSession: { persona_id?: PersonaId } | null | undefined
): PersonaId {
  return loadedPersonaId ?? listedSession?.persona_id ?? undefined;
}

/**
 * Whether the chat header offers the history menu: on an agent page (which has
 * no session until the first message) or inside an agent or flow chat.
 */
export function shouldShowChatHistory(
  focus: { isAgent(): boolean; isChat(): boolean },
  chatPersonaId: PersonaId
): boolean {
  if (focus.isAgent()) return true;
  return focus.isChat() && isAgentChatSession({ persona_id: chatPersonaId });
}
