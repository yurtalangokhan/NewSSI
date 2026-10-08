/**
 * @jest-environment jsdom
 *
 * cleanupOldSessions() existed but no action ever called it, so the
 * sessions Map grew for the lifetime of the tab — one entry (message
 * tree, AbortController) per chat session ever opened.
 */
import { describe, expect, it, beforeEach, afterEach } from "@jest/globals";

import { renderHook } from "@testing-library/react";

import {
  MAX_SESSIONS,
  useChatSessionPersonaId,
  useChatSessionStore,
} from "./useChatSessionStore";

describe("useChatSessionStore session bounds", () => {
  beforeEach(() => {
    useChatSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    });
    // cleanupOldSessions ranks sessions by lastAccessed; creating dozens
    // of them in the same tick would tie every timestamp to the
    // millisecond, so advance the clock between each one.
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("evicts the oldest sessions past the limit on createSession", () => {
    const store = useChatSessionStore.getState();
    for (let i = 0; i < MAX_SESSIONS + 25; i += 1) {
      store.createSession(`s${i}`);
      jest.advanceTimersByTime(1);
    }
    expect(useChatSessionStore.getState().sessions.size).toBeLessThanOrEqual(
      MAX_SESSIONS
    );
  });

  it("evicts the oldest sessions past the limit on setCurrentSession", () => {
    const store = useChatSessionStore.getState();
    for (let i = 0; i < MAX_SESSIONS + 25; i += 1) {
      store.setCurrentSession(`s${i}`);
      jest.advanceTimersByTime(1);
    }
    expect(useChatSessionStore.getState().sessions.size).toBeLessThanOrEqual(
      MAX_SESSIONS
    );
  });

  it("keeps a re-touched session over one that was never revisited", () => {
    const store = useChatSessionStore.getState();
    store.createSession("a");
    jest.advanceTimersByTime(1);
    store.createSession("b");
    jest.advanceTimersByTime(1);

    // Fill up to exactly the limit with sessions newer than "a" and "b".
    for (let i = 0; i < MAX_SESSIONS - 2; i += 1) {
      store.createSession(`filler${i}`);
      jest.advanceTimersByTime(1);
    }

    // Re-touch "a" so it now outranks "b" and every filler by recency.
    store.setCurrentSession("a");
    jest.advanceTimersByTime(1);

    // One more session pushes the count over the limit, forcing exactly
    // one eviction: whichever session is least recently accessed.
    store.createSession("overflow");

    const sessions = useChatSessionStore.getState().sessions;
    expect(sessions.has("a")).toBe(true);
    expect(sessions.has("b")).toBe(false);
  });

  it("aborts the in-flight controller of an evicted session", () => {
    const store = useChatSessionStore.getState();
    store.createSession("evict-me");
    const controller = useChatSessionStore
      .getState()
      .sessions.get("evict-me")!.abortController;
    jest.advanceTimersByTime(1);

    for (let i = 0; i < MAX_SESSIONS + 5; i += 1) {
      store.createSession(`filler${i}`);
      jest.advanceTimersByTime(1);
    }

    expect(useChatSessionStore.getState().sessions.has("evict-me")).toBe(false);
    expect(controller.signal.aborted).toBe(true);
  });
});

describe("useChatSessionPersonaId", () => {
  beforeEach(() => {
    useChatSessionStore.setState({
      currentSessionId: null,
      sessions: new Map(),
    });
  });

  it("returns the persona of the given loaded session and undefined otherwise", () => {
    useChatSessionStore.getState().initializeSession("s1", {
      persona_id: 7,
    } as never);
    const { result } = renderHook(() => ({
      known: useChatSessionPersonaId("s1"),
      unknown: useChatSessionPersonaId("nope"),
      none: useChatSessionPersonaId(null),
    }));
    expect(result.current).toEqual({
      known: 7,
      unknown: undefined,
      none: undefined,
    });
  });
});
