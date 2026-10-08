/**
 * Whether a chat session should be handed to the auto-naming endpoint.
 *
 * The backend always sends a non-empty `description`: an unnamed session gets
 * a readable stand-in so the sidebar is never blank, and a session named while
 * the model was unreachable gets a truncation of its own first question. Both
 * look exactly like a real title on the wire, which is why `name_provisional`
 * exists — it is the only thing separating "this is the title" from "this is
 * the best we could do at the time".
 */
export interface NameableSession {
  description?: string | null;
  name_provisional?: boolean;
}

export function needsGeneratedName(session: NameableSession): boolean {
  if (!session.description?.trim()) {
    return true;
  }
  return session.name_provisional === true;
}
