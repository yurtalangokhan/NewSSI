import { PacketType } from "@/lib/api/domains/chat/message-types";
import { handleSSEStream } from "@/lib/search/streamingUtils";
import type { ActiveRunInfo, RunMetaPacket } from "./run-types";

export type { ActiveRunInfo };

/**
 * Base of the errors a run stream raises. The tsconfig targets es5, where
 * subclassed builtins lose their prototype chain and `instanceof` would always
 * be false, so the chain is restored here once for every subclass.
 */
abstract class ChatRunStreamError extends Error {
  constructor(message: string, name: string) {
    super(message);
    this.name = name;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ChatRunActiveError extends ChatRunStreamError {
  constructor(readonly runId: string | null) {
    super(
      "A response is still being generated in this chat",
      "ChatRunActiveError"
    );
  }
}
export class ChatRunResyncRequiredError extends ChatRunStreamError {
  constructor(readonly runId: string | null) {
    super(
      "The live stream can no longer be replayed",
      "ChatRunResyncRequiredError"
    );
  }
}
export class ChatRunExpiredError extends ChatRunStreamError {
  constructor(readonly runId: string) {
    super("The run is no longer available", "ChatRunExpiredError");
  }
}

export interface ResumableChatStreamDeps {
  open: (signal: AbortSignal) => Promise<Response>;
  attach: (runId: string, signal: AbortSignal) => Promise<Response>;
  findActiveRun: (signal: AbortSignal) => Promise<ActiveRunInfo | null>;
  clientRequestId: string | null;
  signal: AbortSignal;
  /** Known run id (page-load attach): skips active-run discovery. */
  initialRunId?: string;
  /**
   * The first stream is a replay of a run already under way (page-load
   * attach) rather than a fresh send, so it starts in replay.
   */
  initialReplay?: boolean;
  /**
   * Called when the stream enters or leaves replay: it enters on a replaying
   * attach (the initial one for `initialReplay`, and every re-attach) and
   * leaves at the reader's `caught_up` packet, or when the stream ends or
   * fails. Fires only on change, and always between the packets it separates.
   */
  onReplayChange?: (replaying: boolean) => void;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  backoffMs?: (attempt: number) => number;
  maxConsecutiveFailures?: number;
}

/**
 * Re-attach delay: the exponential step (500 ms doubling, capped at 10 s) with
 * "equal jitter", a random point in its upper half. After a deploy or a
 * network blip every open tab reconnects at once and replays its run; a wide
 * spread keeps those replays from reaching the server in the same instant.
 */
export function reconnectDelayMs(
  attempt: number,
  random: () => number = Math.random
): number {
  const step = Math.min(10_000, 500 * 2 ** (attempt - 1));
  return step / 2 + Math.floor(random() * (step / 2));
}

const defaultBackoff = (attempt: number) => reconnectDelayMs(attempt);

const abortableSleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true }
    );
  });

/**
 * One chat turn's packets, surviving network drops: every re-attach replays the
 * run from the start and suppresses what was already delivered, because the
 * packet parser's turn/tool bookkeeping must see the whole stream. A user
 * abort never re-attaches and never calls Stop — Stop is a separate call.
 */
export async function* resumableChatStream(
  deps: ResumableChatStreamDeps
): AsyncGenerator<PacketType, void, unknown> {
  const sleep = deps.sleep ?? abortableSleep;
  const backoff = deps.backoffMs ?? defaultBackoff;
  const maxFailures = deps.maxConsecutiveFailures ?? 8;
  let runId: string | null = deps.initialRunId ?? null;
  let delivered = 0;
  let ended = false;
  let resync = false;
  let failures = 0;
  let lastError: unknown = null;
  let replaying = false;
  const setReplaying = (next: boolean) => {
    if (next === replaying) return;
    replaying = next;
    deps.onReplayChange?.(next);
  };
  const onRunMeta = (meta: RunMetaPacket) => {
    if (meta.type === "run_started") runId = meta.run_id;
    else if (meta.type === "run_end") ended = true;
    else if (meta.type === "caught_up") setReplaying(false);
    else resync = true;
  };
  const onEventId = (seq: number) => {
    if (seq > delivered) {
      delivered = seq;
      failures = 0;
    }
  };

  if (deps.initialReplay) setReplaying(true);
  try {
    let response: Response | null = null;
    try {
      response = await deps.open(deps.signal);
    } catch (error) {
      if (deps.signal.aborted) return;
      lastError = error;
    }
    if (response?.status === 409) {
      // The backend's error envelope: the holder rides in error.details.
      const body = (await response.json().catch(() => ({}))) as {
        error?: { details?: { run_id?: string } };
      };
      throw new ChatRunActiveError(body.error?.details?.run_id ?? null);
    }
    if (response && !response.ok)
      throw new Error(`HTTP error! status: ${response.status}`);

    while (true) {
      if (response) {
        try {
          yield* handleSSEStream<PacketType>(response, deps.signal, {
            suppressThroughSeq: delivered,
            onEventId,
            onRunMeta,
          });
        } catch (error) {
          if (deps.signal.aborted) return;
          lastError = error;
        }
      }
      if (deps.signal.aborted || ended) return;
      if (resync) throw new ChatRunResyncRequiredError(runId);
      if (runId === null) {
        const active = await deps.findActiveRun(deps.signal).catch(() => null);
        if (!active || active.client_request_id !== deps.clientRequestId) {
          // The POST itself died: rethrow its error. A stream that merely ended
          // without run meta (legacy backend, empty reply) ends cleanly instead,
          // which keeps the old sendMessage behavior observable.
          if (lastError) throw lastError;
          return;
        }
        runId = active.run_id;
      }
      failures += 1;
      if (failures > maxFailures)
        throw lastError ?? new Error("Stream disconnected");
      await sleep(backoff(failures), deps.signal);
      if (deps.signal.aborted) return;
      try {
        response = await deps.attach(runId, deps.signal);
      } catch (error) {
        if (deps.signal.aborted) return;
        lastError = error;
        response = null;
        continue;
      }
      if (response.status === 404) throw new ChatRunExpiredError(runId);
      if (!response.ok) {
        lastError = new Error(`HTTP error! status: ${response.status}`);
        response = null;
      } else {
        // Whatever this stream sends before its caught_up is history.
        setReplaying(true);
      }
    }
  } finally {
    // Nothing after this point is a replay, however the stream ended.
    setReplaying(false);
  }
}

export interface SendAfterOwnRunEndsDeps {
  findActiveRun: () => Promise<ActiveRunInfo | null>;
  /** True for a client_request_id this tab sent itself. */
  isOwnRequest: (clientRequestId: string | null) => boolean;
  signal: AbortSignal;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  backoffMs?: (attempt: number) => number;
  maxAttempts?: number;
}

// 300 ms doubling to 2 s: ~15 s over the default attempts, enough for a
// stopped run on another instance to reach its terminal state (heartbeat +
// cancel grace + finalization).
const ownRunBackoff = (attempt: number) =>
  Math.min(2_000, 300 * 2 ** (attempt - 1));

/**
 * Sends, and when the thread is still held by a run this tab started itself
 * (one it just stopped, or one that is finishing), waits for that run to
 * release the thread and sends again instead of surfacing a 409. A 409 on
 * open is raised before anything is yielded or persisted, so a retry is
 * safe. A run held by another tab or device is rethrown for the caller.
 */
export async function* sendAfterOwnRunEnds(
  send: () => AsyncGenerator<PacketType, void, unknown>,
  deps: SendAfterOwnRunEndsDeps
): AsyncGenerator<PacketType, void, unknown> {
  const sleep = deps.sleep ?? abortableSleep;
  const backoff = deps.backoffMs ?? ownRunBackoff;
  const maxAttempts = deps.maxAttempts ?? 10;
  for (let attempt = 1; ; attempt += 1) {
    try {
      yield* send();
      return;
    } catch (error) {
      if (!(error instanceof ChatRunActiveError) || attempt >= maxAttempts) {
        throw error;
      }
      let active: ActiveRunInfo | null = null;
      let lookupFailed = false;
      try {
        active = await deps.findActiveRun();
      } catch {
        lookupFailed = true;
      }
      if (active && !deps.isOwnRequest(active.client_request_id)) throw error;
      // A held thread (ours) or an unanswered lookup both need time. Only a
      // lookup that says "nothing is running" means the thread was released
      // in the meantime, so that one retries at once.
      if (active || lookupFailed) await sleep(backoff(attempt), deps.signal);
      if (deps.signal.aborted) return;
    }
  }
}

/**
 * Page-load attach to a run discovered via the active-run lookup: the run id
 * is known up front, so there is nothing to discover and no idempotency key
 * to match.
 */
export function attachToRunStream(
  runId: string,
  signal: AbortSignal,
  deps: Partial<ResumableChatStreamDeps> &
    Pick<ResumableChatStreamDeps, "attach">
): AsyncGenerator<PacketType, void, unknown> {
  return resumableChatStream({
    ...deps,
    open: (s) => deps.attach(runId, s),
    findActiveRun: deps.findActiveRun ?? (async () => null),
    clientRequestId: deps.clientRequestId ?? null,
    initialRunId: runId,
    // The run is already under way: whatever the first stream sends is history.
    initialReplay: true,
    signal,
  });
}
