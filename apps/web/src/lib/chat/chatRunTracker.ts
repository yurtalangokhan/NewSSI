import type { ActiveRunInfo } from "@/lib/api/domains/chat/run-types";

/** Sends and runs kept in memory before the oldest are forgotten. */
const DEFAULT_MEMORY = 200;

/** A set that forgets its oldest entries, so a long-lived tab cannot grow it forever. */
class BoundedSet {
  private readonly items = new Set<string>();
  constructor(private readonly capacity: number) {}

  add(value: string) {
    this.items.delete(value);
    this.items.add(value);
    if (this.items.size > this.capacity) {
      const oldest = this.items.values().next().value;
      if (oldest !== undefined) this.items.delete(oldest);
    }
  }

  has(value: string) {
    return this.items.has(value);
  }
}

/**
 * What one tab knows about the chat runs it started or attached to.
 *
 * - its own sends, so a 409 caused by a run this tab started (typically one it
 *   just stopped) is waited out instead of shown;
 * - runs it already rendered to the end or stopped, so re-discovering one
 *   through the active-run lookup while it winds down does not replay it;
 * - the run each session currently streams, and the request id of its send, so
 *   a Stop can name the send even before the server registered its run;
 * - sessions with an attach in progress, since several triggers (page load,
 *   409, visibility, online) can discover the same run at once.
 */
export class ChatRunTracker {
  private readonly ownRequests: BoundedSet;
  private readonly settledRuns: BoundedSet;
  private readonly streamedKey = new Map<string, string>();
  private readonly sendRequestId = new Map<string, string>();
  private readonly attaching = new Set<string>();

  constructor({ memory = DEFAULT_MEMORY }: { memory?: number } = {}) {
    this.ownRequests = new BoundedSet(memory);
    this.settledRuns = new BoundedSet(memory);
  }

  /** The session now streams a send this tab made under `clientRequestId`. */
  beginSend(sessionId: string, clientRequestId: string) {
    this.ownRequests.add(clientRequestId);
    this.streamedKey.set(sessionId, clientRequestId);
    this.sendRequestId.set(sessionId, clientRequestId);
  }

  /** The session now streams a run started elsewhere (an attach). */
  beginAttach(sessionId: string, runId: string) {
    this.streamedKey.set(sessionId, runId);
    this.sendRequestId.delete(sessionId);
  }

  isOwnRequest(clientRequestId: string | null) {
    return clientRequestId !== null && this.ownRequests.has(clientRequestId);
  }

  /** The request id a Stop should name for this session's in-flight send. */
  requestIdOf(sessionId: string) {
    return this.sendRequestId.get(sessionId);
  }

  /** The run (or request) key was rendered to the end or stopped. */
  settle(key: string) {
    this.settledRuns.add(key);
  }

  /** The session's current stream was stopped. */
  settleSession(sessionId: string) {
    const key = this.streamedKey.get(sessionId);
    if (key) this.settle(key);
  }

  isSettled(run: Pick<ActiveRunInfo, "run_id" | "client_request_id">) {
    return (
      this.settledRuns.has(run.run_id) ||
      (run.client_request_id !== null &&
        this.settledRuns.has(run.client_request_id))
    );
  }

  /** False when an attach for this session is already running. */
  tryBeginAttach(sessionId: string) {
    if (this.attaching.has(sessionId)) return false;
    this.attaching.add(sessionId);
    return true;
  }

  endAttach(sessionId: string) {
    this.attaching.delete(sessionId);
  }
}
