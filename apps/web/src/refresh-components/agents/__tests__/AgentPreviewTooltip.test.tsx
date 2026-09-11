import { render, screen } from "@testing-library/react";
import AgentPreviewTooltip, { parseAgentPreview } from "../AgentPreviewTooltip";

describe("parseAgentPreview", () => {
  it("splits the header facts and the optional prompt line", () => {
    const { facts, prompt } = parseAgentPreview(
      "Model: gpt-4o · Tools: 2 · Memory: on\nYou are a helpful support agent."
    );

    expect(facts).toEqual([
      { label: "Model", value: "gpt-4o" },
      { label: "Tools", value: "2" },
      { label: "Memory", value: "on" },
    ]);
    expect(prompt).toBe("You are a helpful support agent.");
  });

  it("omits prompt when the preview has no second line", () => {
    const { prompt } = parseAgentPreview(
      "Model: default · Tools: 0 · Memory: off"
    );
    expect(prompt).toBeUndefined();
  });
});

describe("AgentPreviewTooltip", () => {
  const PREVIEW =
    "Model: gpt-4o · Tools: 2 · Memory: on\nYou are a helpful support agent.";

  it("renders each fact as a distinct labeled row", () => {
    render(<AgentPreviewTooltip preview={PREVIEW} />);

    expect(screen.getByText("Model:")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("Tools:")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Memory:")).toBeInTheDocument();
    expect(screen.getByText("on")).toBeInTheDocument();
  });

  it("colors an 'on' memory value distinctly from an 'off' one", () => {
    const { rerender } = render(<AgentPreviewTooltip preview={PREVIEW} />);
    expect(screen.getByText("on").className).toContain(
      "text-status-success-05"
    );

    rerender(
      <AgentPreviewTooltip preview="Model: default · Tools: 0 · Memory: off" />
    );
    expect(screen.getByText("off").className).not.toContain(
      "text-status-success-05"
    );
  });

  it("shows the prompt preview below the facts when present", () => {
    render(<AgentPreviewTooltip preview={PREVIEW} />);
    expect(
      screen.getByText("You are a helpful support agent.")
    ).toBeInTheDocument();
  });

  it("renders no prompt section when the preview carries only facts", () => {
    render(
      <AgentPreviewTooltip preview="Model: default · Tools: 0 · Memory: off" />
    );
    expect(
      screen.queryByTestId("agent-preview-prompt")
    ).not.toBeInTheDocument();
  });
});
