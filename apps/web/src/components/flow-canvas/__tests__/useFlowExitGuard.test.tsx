import { act, renderHook } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { useFlowExitGuard } from "../hooks/useFlowExitGuard";

const mockSaveDraftNow = jest.fn().mockResolvedValue(undefined);
const mockDiscardDraft = jest.fn().mockResolvedValue(undefined);
jest.mock("../hooks/useFlowDraft", () => ({
  saveDraftNow: (...args: unknown[]) => mockSaveDraftNow(...args),
  discardDraft: (...args: unknown[]) => mockDiscardDraft(...args),
}));

const DEFINITION_ID = "def-1";

describe("useFlowExitGuard", () => {
  beforeEach(() => {
    mockSaveDraftNow.mockClear();
    mockDiscardDraft.mockClear();
  });

  it("exits immediately when there is no draft", async () => {
    const onExited = jest.fn();
    const { result } = renderHook(() =>
      useFlowExitGuard({
        definitionId: DEFINITION_ID,
        store: createFlowStore(),
        hasDraft: false,
        onExited,
      })
    );

    await act(async () => {
      await result.current.requestExit();
    });

    expect(result.current.isConfirmOpen).toBe(false);
    expect(onExited).toHaveBeenCalled();
  });

  it("asks before exiting when a draft exists", async () => {
    const onExited = jest.fn();
    const { result } = renderHook(() =>
      useFlowExitGuard({
        definitionId: DEFINITION_ID,
        store: createFlowStore(),
        hasDraft: true,
        onExited,
      })
    );

    await act(async () => {
      await result.current.requestExit();
    });

    expect(result.current.isConfirmOpen).toBe(true);
    expect(onExited).not.toHaveBeenCalled();
  });

  it("flushes the draft and exits when keeping it", async () => {
    const onExited = jest.fn();
    const store = createFlowStore();
    const { result } = renderHook(() =>
      useFlowExitGuard({
        definitionId: DEFINITION_ID,
        store,
        hasDraft: true,
        onExited,
      })
    );

    await act(async () => {
      await result.current.requestExit();
      await result.current.keepDraft();
    });

    expect(mockSaveDraftNow).toHaveBeenCalledWith(DEFINITION_ID, store);
    expect(mockDiscardDraft).not.toHaveBeenCalled();
    expect(onExited).toHaveBeenCalled();
  });

  it("deletes the draft before exiting when discarding", async () => {
    const onExited = jest.fn();
    const { result } = renderHook(() =>
      useFlowExitGuard({
        definitionId: DEFINITION_ID,
        store: createFlowStore(),
        hasDraft: true,
        onExited,
      })
    );

    await act(async () => {
      await result.current.requestExit();
      await result.current.discardAndExit();
    });

    expect(mockDiscardDraft).toHaveBeenCalledWith(DEFINITION_ID);
    expect(onExited).toHaveBeenCalled();
  });

  it("stays put when cancelled", async () => {
    const onExited = jest.fn();
    const { result } = renderHook(() =>
      useFlowExitGuard({
        definitionId: DEFINITION_ID,
        store: createFlowStore(),
        hasDraft: true,
        onExited,
      })
    );

    await act(async () => {
      await result.current.requestExit();
      result.current.cancel();
    });

    expect(result.current.isConfirmOpen).toBe(false);
    expect(onExited).not.toHaveBeenCalled();
  });
});
