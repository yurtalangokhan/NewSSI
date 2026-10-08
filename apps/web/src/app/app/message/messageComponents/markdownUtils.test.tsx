import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import type { FullChatState } from "@/app/app/message/messageComponents/interfaces";
import { useMarkdownRenderer } from "@/app/app/message/messageComponents/markdownUtils";
import { MermaidRenderError } from "@/components/mermaid/mermaidDiagnostics";

const mockRuntime = { peek: jest.fn(), render: jest.fn(), validate: jest.fn() };
jest.mock("@/components/mermaid/mermaidRuntime", () => ({
  getMermaidRuntime: () => mockRuntime,
}));

const RESULT = {
  svg: '<svg id="mmd1z" viewBox="0 0 10 10"></svg>',
  renderId: "mmd1z",
};
const OPEN = "Akış:\n\n```mermaid\nflowchart LR\n  A[Başvuru] --> B";
const CLOSED = OPEN + "[Belge]\n```\n\nSonra";

interface HarnessProps {
  content: string;
  isStreaming: boolean;
  state?: FullChatState;
}

/** Mirrors MessageTextRenderer: the cursor hack is appended while streaming. */
function Harness({ content, isStreaming, state }: HarnessProps) {
  const { renderedContent } = useMarkdownRenderer(
    isStreaming ? `${content} [*]() ` : content,
    state,
    "text-base",
    undefined,
    { isStreaming }
  );
  return renderedContent;
}

beforeEach(() => {
  mockRuntime.peek.mockReset().mockReturnValue(undefined);
  mockRuntime.render.mockReset().mockResolvedValue(RESULT);
});

describe("chat markdown mermaid routing", () => {
  it("keeps an open fence pending while streaming and never shows the cursor", () => {
    renderWithI18n(<Harness content={OPEN} isStreaming />);

    expect(
      screen.getByRole("status", { name: "Writing diagram · 2 lines" })
    ).toBeInTheDocument();
    expect(screen.getByTestId("mermaid-pending-tail")).toHaveTextContent(
      "A[Başvuru] --> B"
    );
    expect(screen.getByTestId("mermaid-pending-tail")).not.toHaveTextContent(
      "[*]"
    );
    expect(mockRuntime.render).not.toHaveBeenCalled();
  });

  it("renders once the fence closes and is not remounted by later packets", async () => {
    const { rerender } = renderWithI18n(<Harness content={OPEN} isStreaming />);

    rerender(<Harness content={CLOSED} isStreaming />);
    await screen.findByTestId("mermaid-svg");
    fireEvent.click(screen.getByRole("button", { name: "Code" }));
    rerender(<Harness content={`${CLOSED} ve devamı`} isStreaming />);
    rerender(
      <Harness content={`${CLOSED} ve devamı geldi`} isStreaming={false} />
    );

    // The Code toggle survived: the block was not remounted.
    expect(screen.getByTestId("mermaid-source")).toBeInTheDocument();
    expect(mockRuntime.render).toHaveBeenCalledTimes(1);
    expect(mockRuntime.render).toHaveBeenCalledWith(
      "flowchart LR\n  A[Başvuru] --> B[Belge]",
      expect.objectContaining({ key: expect.any(String) }),
      expect.any(AbortSignal)
    );
  });

  it("renders an unclosed fence once the message has stopped", async () => {
    renderWithI18n(<Harness content={OPEN} isStreaming={false} />);

    await waitFor(() =>
      expect(mockRuntime.render).toHaveBeenCalledWith(
        "flowchart LR\n  A[Başvuru] --> B",
        expect.anything(),
        expect.any(AbortSignal)
      )
    );
  });

  it("leaves other languages on CodeBlock", () => {
    const { container } = renderWithI18n(
      <Harness content={"```python\nprint(1)\n```"} isStreaming={false} />
    );

    expect(container.textContent).toContain("print(1)");
    expect(screen.queryByTestId("mermaid-diagram")).not.toBeInTheDocument();
  });

  it("survives a citations update mid-stream without remounting the diagram", async () => {
    const stateA = { citations: { "1": { document_id: "doc-a" } } } as any;
    const stateB = { citations: { "1": { document_id: "doc-b" } } } as any;

    const { rerender } = renderWithI18n(
      <Harness content={CLOSED} isStreaming state={stateA} />
    );
    await screen.findByTestId("mermaid-svg");
    fireEvent.click(screen.getByRole("button", { name: "Code" }));

    // Citations change mid-stream (e.g. a later chunk resolves a reference).
    // The `code` renderer must stay stable, so the Code toggle is preserved.
    rerender(<Harness content={CLOSED} isStreaming state={stateB} />);

    expect(screen.getByTestId("mermaid-source")).toBeInTheDocument();
    expect(mockRuntime.render).toHaveBeenCalledTimes(1);
  });
});

describe("ask the agent to fix", () => {
  const BROKEN = "```mermaid\nflowchart LR\n  A BROKEN B\n```";

  it("sends a templated follow-up with the error and the source", async () => {
    mockRuntime.render.mockReset().mockRejectedValue(
      new MermaidRenderError({
        kind: "parse",
        message: "Expecting 'SEMI'",
        line: 2,
      })
    );
    const onSendFollowUp = jest.fn();
    const state = { agent: {}, onSendFollowUp } as unknown as FullChatState;
    renderWithI18n(
      <Harness content={BROKEN} isStreaming={false} state={state} />
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "Ask the agent to fix" })
    );

    expect(onSendFollowUp).toHaveBeenCalledTimes(1);
    const message = onSendFollowUp.mock.calls[0]![0] as string;
    expect(message).toContain("line 2: Expecting 'SEMI'");
    expect(message).toContain("```mermaid\nflowchart LR\n  A BROKEN B\n```");
  });

  it("hides the action when the surface cannot send", async () => {
    mockRuntime.render.mockReset().mockRejectedValue(
      new MermaidRenderError({
        kind: "parse",
        message: "Expecting 'SEMI'",
        line: 2,
      })
    );
    renderWithI18n(<Harness content={BROKEN} isStreaming={false} />);

    await screen.findByTestId("mermaid-error");
    expect(
      screen.queryByRole("button", { name: "Ask the agent to fix" })
    ).not.toBeInTheDocument();
  });
});
