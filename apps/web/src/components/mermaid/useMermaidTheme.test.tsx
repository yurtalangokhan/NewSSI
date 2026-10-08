import { act, renderHook, waitFor } from "@testing-library/react";
import { useMermaidTheme } from "@/components/mermaid/useMermaidTheme";
import { LightSurface } from "@/components/theme/LightSurface";

afterEach(() => {
  document.documentElement.className = "";
});

describe("useMermaidTheme", () => {
  it("follows the html dark class and changes the cache key", async () => {
    const { result } = renderHook(() => useMermaidTheme());
    const lightKey = result.current.key;
    expect(result.current.darkMode).toBe(false);

    act(() => {
      document.documentElement.classList.add("dark");
    });

    await waitFor(() => expect(result.current.darkMode).toBe(true));
    expect(result.current.key).not.toBe(lightKey);
  });

  it("returns the same object while nothing changes", () => {
    const { result, rerender } = renderHook(() => useMermaidTheme());
    const first = result.current;

    rerender();

    expect(result.current).toBe(first);
  });

  it("follows the enclosing light surface instead of the html dark class", async () => {
    document.documentElement.classList.add("dark");
    const styles = {
      getPropertyValue: (token: string) =>
        token === "--background-tint-00" ? "#ffffff" : "",
      fontFamily: "",
    };
    const spy = jest
      .spyOn(window, "getComputedStyle")
      .mockReturnValue(styles as unknown as CSSStyleDeclaration);

    const { result } = renderHook(() => useMermaidTheme(), {
      wrapper: ({ children }) => (
        <LightSurface enabled>{children}</LightSurface>
      ),
    });

    // A diagram on the document panel's white page must not render with the
    // dark diagram palette even though <html> is dark.
    await waitFor(() => expect(result.current.darkMode).toBe(false));
    expect(result.current.themeVariables.background).toBe("#ffffff");
    spy.mockRestore();
  });
});
