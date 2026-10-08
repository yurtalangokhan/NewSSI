import {
  MinimalPersonaSnapshot,
  Persona,
} from "@/lib/api/domains/agents/types";
import { User } from "@/lib/types";

/**
 * Sentinel email returned by the backend when an agent's owner account
 * could not be resolved (e.g. the owning user was deleted). Must match
 * `_resolve_owner_email`'s fallback in `persona_controller.py`.
 */
export const UNKNOWN_AGENT_OWNER_EMAIL = "Unknown user";

/**
 * Resolves an agent owner's email for display, translating the backend's
 * "owner not found" sentinel into a localized label.
 */
export function resolveAgentOwnerEmail(
  email: string | null | undefined,
  t: (key: string) => string,
  fallback = "Atlas",
  ownerId?: string | null,
  currentUser?: { id?: string; email?: string } | null
): string {
  if (
    ownerId &&
    currentUser?.id &&
    ownerId === currentUser.id &&
    currentUser.email
  ) {
    return currentUser.email;
  }
  if (!email) return fallback;
  if (email === UNKNOWN_AGENT_OWNER_EMAIL) {
    if (
      ownerId &&
      currentUser?.id &&
      ownerId === currentUser.id &&
      currentUser.email
    ) {
      return currentUser.email;
    }
    return t("agentsPage.unknownOwner");
  }
  return email;
}

/**
 * Checks if the given user owns the specified assistant.
 *
 * @param user - The user to check ownership for, or null if no user is logged in
 * @param assistant - The assistant to check ownership of
 * @returns true if the user owns the agent, false otherwise
 */
export function checkUserOwnsAgent(
  user: User | null,
  agent: MinimalPersonaSnapshot | Persona
) {
  return checkUserIdOwnsAgent(user?.id, agent);
}

/**
 * Checks if the given user ID owns the specified assistant.
 *
 * Returns true when a valid user ID exactly matches the agent owner's ID and
 * the agent is not built-in.
 *
 * Returns false if userId is undefined (e.g., user is loading or unauthenticated)
 * to prevent granting ownership access prematurely.
 *
 * @param userId - The user ID to check ownership for
 * @param assistant - The assistant to check ownership of
 * @returns true if the user owns the agent, false otherwise
 */
export function checkUserIdOwnsAgent(
  userId: string | undefined,
  agent: MinimalPersonaSnapshot | Persona
) {
  return !!userId && agent.owner?.id === userId && !agent.builtin_persona;
}

function smallerNumberFirstComparator(a: number, b: number) {
  return a > b ? 1 : -1;
}

function closerToZeroNegativesFirstComparator(a: number, b: number) {
  if (a < 0 && b > 0) return -1;
  if (a > 0 && b < 0) return 1;

  const absA = Math.abs(a);
  const absB = Math.abs(b);
  if (absA === absB) return a > b ? 1 : -1;
  return absA > absB ? 1 : -1;
}

export function personaComparator(
  a: MinimalPersonaSnapshot | Persona,
  b: MinimalPersonaSnapshot | Persona
) {
  if (a.display_priority === null && b.display_priority === null) {
    return closerToZeroNegativesFirstComparator(a.id, b.id);
  }
  if (a.display_priority !== b.display_priority) {
    if (a.display_priority === null) return 1;
    if (b.display_priority === null) return -1;
    return smallerNumberFirstComparator(a.display_priority, b.display_priority);
  }
  return closerToZeroNegativesFirstComparator(a.id, b.id);
}

/**
 * Filters and sorts assistants based on visibility.
 *
 * Only returns assistants that are marked as visible, sorted using the persona comparator.
 *
 * @param assistants - Array of assistants to filter
 * @returns Filtered and sorted array of visible assistants
 */
export function filterAgents(
  assistants: MinimalPersonaSnapshot[]
): MinimalPersonaSnapshot[] {
  let filteredAgents = assistants.filter((assistant) => assistant.is_visible);
  return filteredAgents.sort(personaComparator);
}
