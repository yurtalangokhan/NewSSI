import { act, renderHook, waitFor } from "@testing-library/react";
import { fetchActiveRun } from "@/lib/api/domains/chat/api";
import type { ActiveRunInfo } from "@/lib/api/domains/chat/resumableChatStream";
import useActiveRunRecovery from "./useActiveRunRecovery";

jest.mock("@/lib/api/domains/chat/api", () => ({
  fetchActiveRun: jest.fn(),
}));

const fetchActiveRunMock = jest.mocked(fetchActiveRun);

const run: ActiveRunInfo = {
  run_id: "r1",
  status: "running",
  started_at: 1,
  input_preview: "q",
  client_request_id: null,
};

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  });
}

beforeEach(() => {
  fetchActiveRunMock.mockReset();
  setVisibility("visible");
});

it("attaches once when the tab becomes visible and the chat is idle", async () => {
  fetchActiveRunMock.mockResolvedValue(run);
  const attach = jest.fn().mockResolvedValue(undefined);
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );

  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

  await waitFor(() => expect(attach).toHaveBeenCalledTimes(1));
  expect(fetchActiveRunMock).toHaveBeenCalledWith("s1");
  expect(attach).toHaveBeenCalledWith("s1", run);
});

it("ignores a visibility change to hidden", async () => {
  const attach = jest.fn();
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );

  setVisibility("hidden");
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });

  await Promise.resolve();
  expect(fetchActiveRunMock).not.toHaveBeenCalled();
});

it("attaches when the browser comes back online", async () => {
  fetchActiveRunMock.mockResolvedValue(run);
  const attach = jest.fn().mockResolvedValue(undefined);
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );

  act(() => {
    window.dispatchEvent(new Event("online"));
  });

  await waitFor(() => expect(attach).toHaveBeenCalledWith("s1", run));
});

it("deduplicates triggers that arrive while a lookup is in flight", async () => {
  let resolveLookup: (value: ActiveRunInfo | null) => void = () => {};
  fetchActiveRunMock.mockReturnValue(
    new Promise((resolve) => {
      resolveLookup = resolve;
    })
  );
  const attach = jest.fn().mockResolvedValue(undefined);
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );

  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("online"));
  });
  await act(async () => {
    resolveLookup(run);
  });

  expect(fetchActiveRunMock).toHaveBeenCalledTimes(1);
  expect(attach).toHaveBeenCalledTimes(1);
});

it("does nothing while the chat is busy", async () => {
  const attach = jest.fn();
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => false, attach })
  );

  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("online"));
  });

  await Promise.resolve();
  expect(fetchActiveRunMock).not.toHaveBeenCalled();
  expect(attach).not.toHaveBeenCalled();
});

it("does nothing without a session", async () => {
  const attach = jest.fn();
  renderHook(() =>
    useActiveRunRecovery({ sessionId: null, isIdle: () => true, attach })
  );

  act(() => {
    window.dispatchEvent(new Event("online"));
  });

  await Promise.resolve();
  expect(fetchActiveRunMock).not.toHaveBeenCalled();
});

it("does not attach when no run is active", async () => {
  fetchActiveRunMock.mockResolvedValue(null);
  const attach = jest.fn();
  renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );

  act(() => {
    window.dispatchEvent(new Event("online"));
  });

  await waitFor(() => expect(fetchActiveRunMock).toHaveBeenCalled());
  await Promise.resolve();
  expect(attach).not.toHaveBeenCalled();
});

it("removes its listeners on unmount", async () => {
  const attach = jest.fn();
  const { unmount } = renderHook(() =>
    useActiveRunRecovery({ sessionId: "s1", isIdle: () => true, attach })
  );
  unmount();

  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("online"));
  });

  await Promise.resolve();
  expect(fetchActiveRunMock).not.toHaveBeenCalled();
});
