import { renderHook } from "@testing-library/react";
import { usePanelMermaidFix } from "@/sections/document-panel/usePanelMermaidFix";
import { buildMermaidFixRequest } from "@/components/mermaid/mermaidDiagnostics";

const mockT = (key: string) => key;
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mockT }),
}));
jest.mock("@/components/mermaid/mermaidDiagnostics", () => ({
  buildMermaidFixRequest: jest.fn(() => "Lütfen diyagramı düzelt"),
}));

it("submits the templated fix request as an ordinary send", () => {
  const onSubmit = jest.fn();
  const { result, rerender } = renderHook(() =>
    usePanelMermaidFix(onSubmit, false)
  );
  const first = result.current;
  rerender();
  expect(result.current).toBe(first);

  const diagnostic = { kind: "parse", message: "bad", line: 2 } as const;
  result.current("flowchart LR\n  A BROKEN B", diagnostic);

  expect(buildMermaidFixRequest).toHaveBeenCalledWith(
    expect.any(Function),
    "flowchart LR\n  A BROKEN B",
    diagnostic
  );
  expect(onSubmit).toHaveBeenCalledWith({
    message: "Lütfen diyagramı düzelt",
    currentMessageFiles: [],
    deepResearch: false,
  });
});

it("keeps one callback identity while invoking the latest onSubmit", () => {
  const first = jest.fn();
  const second = jest.fn();
  const { result, rerender } = renderHook(
    ({ onSubmit, deepResearch }) => usePanelMermaidFix(onSubmit, deepResearch),
    { initialProps: { onSubmit: first, deepResearch: false } }
  );
  const callback = result.current;

  rerender({ onSubmit: second, deepResearch: true });
  expect(result.current).toBe(callback);

  callback("src", { kind: "parse", message: "bad", line: 1 } as const);
  expect(first).not.toHaveBeenCalled();
  expect(second).toHaveBeenCalledWith(
    expect.objectContaining({ deepResearch: true })
  );
});
