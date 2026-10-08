import React from "react";
import { render, renderHook } from "@testing-library/react";
import useResolvedColorMode from "@/hooks/useResolvedColorMode";

let mockResolvedTheme: string | undefined;
jest.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: mockResolvedTheme }),
}));

/** Records every value the hook returns, in render order. */
function renderRecording(): string[] {
  const seen: string[] = [];
  function Probe() {
    const mode = useResolvedColorMode();
    seen.push(mode);
    return null;
  }
  render(<Probe />);
  return seen;
}

describe("useResolvedColorMode", () => {
  beforeEach(() => {
    mockResolvedTheme = undefined;
  });

  it("returns dark after mount when the resolved theme is dark", () => {
    mockResolvedTheme = "dark";

    const { result } = renderHook(() => useResolvedColorMode());

    expect(result.current).toBe("dark");
  });

  it.each(["light", undefined])(
    "returns light after mount when the resolved theme is %s",
    (theme) => {
      mockResolvedTheme = theme;

      const { result } = renderHook(() => useResolvedColorMode());

      expect(result.current).toBe("light");
    }
  );

  it("returns light on the first render even when the client theme is dark, so hydration matches the server", () => {
    mockResolvedTheme = "dark";

    const seen = renderRecording();

    expect(seen[0]).toBe("light");
    expect(seen.at(-1)).toBe("dark");
  });
});
