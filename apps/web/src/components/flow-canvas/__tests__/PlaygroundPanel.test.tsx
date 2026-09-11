import { fireEvent, render, screen } from "@testing-library/react";
import { PlaygroundPanel } from "../components/PlaygroundPanel";
import type { PlaygroundMessage } from "../hooks/usePlaygroundRun";

const mockSend = jest.fn();
const mockRetry = jest.fn();
const mockClear = jest.fn();
const mockUsePlaygroundRun = jest.fn();

jest.mock("../hooks/usePlaygroundRun", () => ({
  usePlaygroundRun: (...args: unknown[]) => mockUsePlaygroundRun(...args),
}));

const DEFAULT_MESSAGES: PlaygroundMessage[] = [
  { role: "user", content: "Test query" },
  { role: "assistant", content: "Test response" },
];

function mockRun(
  overrides: Partial<ReturnType<typeof mockUsePlaygroundRun>> = {}
) {
  mockUsePlaygroundRun.mockReturnValue({
    messages: DEFAULT_MESSAGES,
    isRunning: false,
    error: null,
    send: mockSend,
    retry: mockRetry,
    clear: mockClear,
    ...overrides,
  });
}

describe("PlaygroundPanel", () => {
  beforeEach(() => {
    mockRun();
  });

  it("44.7 — renders draft mode banner and messages when open", () => {
    const onClose = jest.fn();
    render(
      <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
    );

    expect(screen.getByTestId("playground-panel")).toBeInTheDocument();
    expect(screen.getByTestId("playground-draft-banner")).toHaveTextContent(
      "Playground — running your draft, not the published version"
    );
    expect(screen.getByTestId("playground-message-user")).toHaveTextContent(
      "Test query"
    );
    expect(
      screen.getByTestId("playground-message-assistant")
    ).toHaveTextContent("Test response");
  });

  it("does not render when open is false", () => {
    const onClose = jest.fn();
    const { container } = render(
      <PlaygroundPanel definitionId="def-1" open={false} onClose={onClose} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders localized send button label", () => {
    const onClose = jest.fn();
    render(
      <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
    );

    expect(screen.getByTestId("playground-send")).toHaveTextContent("Send");
  });

  it("calls onClose when close button clicked", () => {
    const onClose = jest.fn();
    render(
      <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
    );

    fireEvent.click(screen.getByTestId("playground-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows an unsaved-flow banner instead of the draft banner when definitionId is null", () => {
    const onClose = jest.fn();
    render(
      <PlaygroundPanel definitionId={null} open={true} onClose={onClose} />
    );

    expect(screen.getByTestId("playground-draft-banner")).toHaveTextContent(
      "Playground — testing your unsaved flow, nothing is stored"
    );
  });

  it("does not let its submit event bubble to an ancestor form (would otherwise submit the create-agent form and navigate away)", () => {
    const onClose = jest.fn();
    const outerSubmit = jest.fn((e: React.FormEvent) => e.preventDefault());

    render(
      <form onSubmit={outerSubmit}>
        <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
      </form>
    );

    fireEvent.change(screen.getByTestId("playground-input"), {
      target: { value: "test" },
    });
    fireEvent.click(screen.getByTestId("playground-send"));

    expect(mockSend).toHaveBeenCalledWith("test", []);
    expect(outerSubmit).not.toHaveBeenCalled();
  });

  describe("file attachments", () => {
    it("shows a removable chip for a picked file and includes it in send()", () => {
      const onClose = jest.fn();
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
      );

      const file = new File(["hello"], "notes.txt", { type: "text/plain" });
      fireEvent.change(screen.getByTestId("playground-file-input"), {
        target: { files: [file] },
      });

      expect(screen.getByTestId("playground-attached-files")).toHaveTextContent(
        "notes.txt"
      );

      fireEvent.change(screen.getByTestId("playground-input"), {
        target: { value: "check this" },
      });
      fireEvent.click(screen.getByTestId("playground-send"));

      expect(mockSend).toHaveBeenCalledWith("check this", [file]);
      // Cleared after send, same as the text input.
      expect(
        screen.queryByTestId("playground-attached-files")
      ).not.toBeInTheDocument();
    });

    it("removes a picked file when its chip's remove button is clicked, before it's ever sent", () => {
      const onClose = jest.fn();
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
      );

      const file = new File(["hello"], "notes.txt", { type: "text/plain" });
      fireEvent.change(screen.getByTestId("playground-file-input"), {
        target: { files: [file] },
      });
      expect(
        screen.getByTestId("playground-attached-files")
      ).toBeInTheDocument();

      fireEvent.click(
        screen.getByRole("button", { name: /remove attachment/i })
      );

      expect(
        screen.queryByTestId("playground-attached-files")
      ).not.toBeInTheDocument();
    });

    it("allows submitting a file with no typed text", () => {
      const onClose = jest.fn();
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={onClose} />
      );

      const file = new File(["data"], "report.pdf", {
        type: "application/pdf",
      });
      fireEvent.change(screen.getByTestId("playground-file-input"), {
        target: { files: [file] },
      });

      expect(screen.getByTestId("playground-send")).not.toBeDisabled();
      fireEvent.click(screen.getByTestId("playground-send"));

      expect(mockSend).toHaveBeenCalledWith("", [file]);
    });
  });

  describe("reasoning (Thinking…) block", () => {
    it("shows the live reasoning text, expanded, while isThinking is true", () => {
      mockRun({
        messages: [
          { role: "user", content: "hi" },
          {
            role: "assistant",
            content: "",
            reasoning: "pondering the question",
            isThinking: true,
          },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      expect(
        screen.getByTestId("playground-reasoning-content")
      ).toHaveTextContent("pondering the question");
    });

    it("collapses the reasoning text by default once thinking is done, revealing it on toggle", () => {
      mockRun({
        messages: [
          { role: "user", content: "hi" },
          {
            role: "assistant",
            content: "Here's the answer.",
            reasoning: "already thought this through",
            isThinking: false,
          },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      expect(
        screen.queryByTestId("playground-reasoning-content")
      ).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId("playground-reasoning-toggle"));
      expect(
        screen.getByTestId("playground-reasoning-content")
      ).toHaveTextContent("already thought this through");
    });

    it("renders no reasoning block at all when the message has no reasoning text", () => {
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      expect(
        screen.queryByTestId("playground-reasoning-toggle")
      ).not.toBeInTheDocument();
    });
  });

  describe("tool call blocks", () => {
    it("shows a running tool call expanded with its arguments", () => {
      mockRun({
        messages: [
          { role: "user", content: "ara" },
          {
            role: "assistant",
            content: "",
            toolCalls: [
              {
                callId: "t1",
                name: "perform_search",
                input: { query: "Türksat tarihi", search_mode: "Web" },
                status: "running",
              },
            ],
          },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      const block = screen.getByTestId("playground-tool-call");
      expect(block).toHaveTextContent(/PERFORM_SEARCH/i);
      expect(block).toHaveTextContent('"query"');
      expect(block).toHaveTextContent("Türksat tarihi");
    });

    it("collapses a completed tool call, revealing arguments and output on toggle", () => {
      mockRun({
        messages: [
          { role: "user", content: "ara" },
          {
            role: "assistant",
            content: "Done.",
            toolCalls: [
              {
                callId: "t1",
                name: "perform_search",
                input: { query: "Türksat" },
                output: [{ title: "Türksat - Vikipedi" }],
                status: "done",
              },
            ],
          },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      expect(
        screen.queryByTestId("playground-tool-call-content")
      ).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId("playground-tool-call-toggle"));
      const content = screen.getByTestId("playground-tool-call-content");
      expect(content).toHaveTextContent('"query"');
      expect(content).toHaveTextContent("Türksat - Vikipedi");
    });
  });

  describe("run stats (tokens + duration)", () => {
    it("renders formatted duration and token count with a breakdown tooltip", () => {
      mockRun({
        messages: [
          { role: "user", content: "q" },
          {
            role: "assistant",
            content: "answer",
            usage: {
              inputTokens: 33800,
              outputTokens: 370,
              totalTokens: 34170,
            },
            durationMs: 66300,
          },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      const stats = screen.getByTestId("playground-message-stats");
      expect(stats).toHaveTextContent("66.3s");
      expect(stats).toHaveTextContent("34.2K");
      expect(stats.getAttribute("title")).toMatch(/33800/);
      expect(stats.getAttribute("title")).toMatch(/370/);
    });

    it("renders no stats row when the message has neither usage nor duration", () => {
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );
      expect(
        screen.queryByTestId("playground-message-stats")
      ).not.toBeInTheDocument();
    });
  });

  describe("message toolbar (copy + retry)", () => {
    it("copies the assistant message content to the clipboard", async () => {
      const writeText = jest.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });

      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );
      fireEvent.click(screen.getByTestId("playground-copy"));

      expect(writeText).toHaveBeenCalledWith("Test response");
    });

    it("shows a retry button only on the last assistant message and calls retry()", () => {
      mockRun({
        messages: [
          { role: "user", content: "first" },
          { role: "assistant", content: "old answer" },
          { role: "user", content: "second" },
          { role: "assistant", content: "latest answer" },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      const retryButtons = screen.getAllByTestId("playground-retry");
      expect(retryButtons).toHaveLength(1);

      fireEvent.click(retryButtons[0]!);
      expect(mockRetry).toHaveBeenCalledTimes(1);
    });

    it("hides copy and retry on the still-streaming trailing assistant message", () => {
      mockRun({
        isRunning: true,
        messages: [
          { role: "user", content: "first" },
          { role: "assistant", content: "settled answer" },
          { role: "user", content: "second" },
          { role: "assistant", content: "streaming" },
        ],
      });
      render(
        <PlaygroundPanel definitionId="def-1" open={true} onClose={jest.fn()} />
      );

      // The completed earlier turn keeps its copy affordance...
      expect(screen.getAllByTestId("playground-copy")).toHaveLength(1);
      // ...but the in-flight turn shows neither copy nor retry yet.
      expect(screen.queryByTestId("playground-retry")).not.toBeInTheDocument();
    });
  });
});
