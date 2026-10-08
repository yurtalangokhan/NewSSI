import { act, renderHook, waitFor } from "@testing-library/react";
import { MermaidRenderError } from "@/components/mermaid/mermaidDiagnostics";
import {
  buildMermaidTheme,
  type MermaidThemeConfig,
} from "@/components/mermaid/mermaidTheme";
import { useMermaidRender } from "@/components/mermaid/useMermaidRender";

const mockRuntime = { peek: jest.fn(), render: jest.fn() };
jest.mock("@/components/mermaid/mermaidRuntime", () => ({
  getMermaidRuntime: () => mockRuntime,
}));

const LIGHT = buildMermaidTheme(() => "", {
  darkMode: false,
  fontFamily: "sans-serif",
});
const DARK = buildMermaidTheme(() => "", {
  darkMode: true,
  fontFamily: "sans-serif",
});
const FIRST = { svg: '<svg id="mmd1z"></svg>', renderId: "mmd1z" };
const SECOND = { svg: '<svg id="mmd2z"></svg>', renderId: "mmd2z" };

interface Props {
  source: string;
  isComplete: boolean;
  theme: MermaidThemeConfig;
}

function setup(initialProps: Props) {
  return renderHook(
    (props: Props) =>
      useMermaidRender(props.source, props.isComplete, props.theme),
    { initialProps }
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

beforeEach(() => {
  mockRuntime.peek.mockReset().mockReturnValue(undefined);
  mockRuntime.render.mockReset();
});

describe("useMermaidRender", () => {
  it("stays pending and never renders while the fence is open", () => {
    const { result } = setup({
      source: "flowchart LR\n  A",
      isComplete: false,
      theme: LIGHT,
    });

    expect(result.current).toEqual({ status: "pending", lastGood: null });
    expect(mockRuntime.render).not.toHaveBeenCalled();
  });

  it("renders once the fence closes", async () => {
    mockRuntime.render.mockResolvedValue(FIRST);
    const { result, rerender } = setup({
      source: "flowchart LR\n  A",
      isComplete: false,
      theme: LIGHT,
    });

    rerender({ source: "flowchart LR\n  A", isComplete: true, theme: LIGHT });

    await waitFor(() =>
      expect(result.current).toEqual({ status: "rendered", result: FIRST })
    );
    expect(mockRuntime.render).toHaveBeenCalledTimes(1);
  });

  it("starts rendered from the cache without a pending frame", () => {
    mockRuntime.peek.mockReturnValue(FIRST);

    const { result } = setup({
      source: "flowchart LR\n  A",
      isComplete: true,
      theme: LIGHT,
    });

    expect(result.current).toEqual({ status: "rendered", result: FIRST });
    expect(mockRuntime.render).not.toHaveBeenCalled();
  });

  it("keeps the last good svg when a later source fails", async () => {
    mockRuntime.render.mockResolvedValueOnce(FIRST).mockRejectedValueOnce(
      new MermaidRenderError({
        kind: "parse",
        message: "Expecting 'SEMI'",
        line: 2,
      })
    );
    const { result, rerender } = setup({
      source: "flowchart LR\n  A",
      isComplete: true,
      theme: LIGHT,
    });
    await waitFor(() => expect(result.current.status).toBe("rendered"));

    rerender({
      source: "flowchart LR\n  A BROKEN",
      isComplete: true,
      theme: LIGHT,
    });

    await waitFor(() =>
      expect(result.current).toEqual({
        status: "error",
        diagnostic: { kind: "parse", message: "Expecting 'SEMI'", line: 2 },
        lastGood: FIRST,
      })
    );
  });

  it("ignores a result that arrives after the source changed", async () => {
    const gate = deferred<typeof FIRST>();
    mockRuntime.render
      .mockReturnValueOnce(gate.promise)
      .mockResolvedValueOnce(SECOND);
    const { result, rerender } = setup({
      source: "flowchart LR\n  A",
      isComplete: true,
      theme: LIGHT,
    });

    rerender({ source: "flowchart LR\n  B", isComplete: true, theme: LIGHT });
    await waitFor(() =>
      expect(result.current).toEqual({ status: "rendered", result: SECOND })
    );
    await act(async () => {
      gate.resolve(FIRST);
      await gate.promise;
    });

    expect(result.current).toEqual({ status: "rendered", result: SECOND });
  });

  it("re-renders with the new theme and shows the old svg meanwhile", async () => {
    const gate = deferred<typeof SECOND>();
    mockRuntime.render
      .mockResolvedValueOnce(FIRST)
      .mockReturnValueOnce(gate.promise);
    const { result, rerender } = setup({
      source: "flowchart LR\n  A",
      isComplete: true,
      theme: LIGHT,
    });
    await waitFor(() => expect(result.current.status).toBe("rendered"));

    rerender({ source: "flowchart LR\n  A", isComplete: true, theme: DARK });

    await waitFor(() =>
      expect(result.current).toEqual({ status: "pending", lastGood: FIRST })
    );
    expect(mockRuntime.render).toHaveBeenLastCalledWith(
      "flowchart LR\n  A",
      DARK,
      expect.any(AbortSignal)
    );
    await act(async () => {
      gate.resolve(SECOND);
      await gate.promise;
    });
    expect(result.current).toEqual({ status: "rendered", result: SECOND });
  });

  it("aborts the runtime request when the hook unmounts or the source changes", () => {
    mockRuntime.render.mockReturnValue(new Promise(() => {}));
    const { rerender, unmount } = setup({
      source: "A",
      isComplete: true,
      theme: LIGHT,
    });
    const first = mockRuntime.render.mock.calls[0]![2] as AbortSignal;
    expect(first.aborted).toBe(false);

    rerender({ source: "B", isComplete: true, theme: LIGHT });
    expect(first.aborted).toBe(true);
    const second = mockRuntime.render.mock.calls[1]![2] as AbortSignal;
    expect(second.aborted).toBe(false);

    unmount();
    expect(second.aborted).toBe(true);
  });
});
