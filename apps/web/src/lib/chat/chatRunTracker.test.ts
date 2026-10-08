import { ChatRunTracker } from "./chatRunTracker";

const run = (run_id: string, client_request_id: string | null = null) => ({
  run_id,
  client_request_id,
});

describe("ChatRunTracker", () => {
  it("remembers a send as this tab's own and names it for a Stop", () => {
    const tracker = new ChatRunTracker();
    tracker.beginSend("s1", "req-1");

    expect(tracker.isOwnRequest("req-1")).toBe(true);
    expect(tracker.isOwnRequest("someone-else")).toBe(false);
    expect(tracker.isOwnRequest(null)).toBe(false);
    expect(tracker.requestIdOf("s1")).toBe("req-1");
  });

  it("an attach streams a run it did not send, so there is no request id to name", () => {
    const tracker = new ChatRunTracker();
    tracker.beginSend("s1", "req-1");
    tracker.beginAttach("s1", "run-9");

    expect(tracker.requestIdOf("s1")).toBeUndefined();
  });

  it("settling a session marks the run it streams, by the key it streams under", () => {
    const tracker = new ChatRunTracker();
    tracker.beginSend("s1", "req-1");
    tracker.settleSession("s1");

    expect(tracker.isSettled(run("run-1", "req-1"))).toBe(true);
    expect(tracker.isSettled(run("run-2", "req-2"))).toBe(false);
  });

  it("a run counts as settled by its run id or by the request that started it", () => {
    const tracker = new ChatRunTracker();
    tracker.settle("run-1");
    tracker.settle("req-2");

    expect(tracker.isSettled(run("run-1"))).toBe(true);
    expect(tracker.isSettled(run("run-x", "req-2"))).toBe(true);
    expect(tracker.isSettled(run("run-y", null))).toBe(false);
  });

  it("allows one attach at a time per session", () => {
    const tracker = new ChatRunTracker();

    expect(tracker.tryBeginAttach("s1")).toBe(true);
    expect(tracker.tryBeginAttach("s1")).toBe(false);
    expect(tracker.tryBeginAttach("s2")).toBe(true);
    tracker.endAttach("s1");
    expect(tracker.tryBeginAttach("s1")).toBe(true);
  });

  it("forgets the oldest runs and requests beyond its memory so a long session does not grow without bound", () => {
    const tracker = new ChatRunTracker({ memory: 3 });
    for (const id of ["a", "b", "c", "d"]) {
      tracker.settle(id);
      tracker.beginSend("s", id);
    }

    expect(tracker.isSettled(run("a"))).toBe(false);
    expect(tracker.isSettled(run("d"))).toBe(true);
    expect(tracker.isOwnRequest("a")).toBe(false);
    expect(tracker.isOwnRequest("d")).toBe(true);
  });
});
