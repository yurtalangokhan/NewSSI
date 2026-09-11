import { fireEvent, render, screen } from "@testing-library/react";
import { FlowDiffList } from "../FlowDiffList";
import type { FlowDiffEntry } from "../../utils/compile";

describe("FlowDiffList", () => {
  it("shows the empty state when there are no changes", () => {
    render(<FlowDiffList entries={[]} onExpandField={jest.fn()} />);
    expect(screen.getByTestId("version-diff-empty")).toBeInTheDocument();
  });

  it("renders a short field change inline, old and new value both visible", () => {
    const entries: FlowDiffEntry[] = [
      {
        kind: "field-changed",
        nodeId: "chatbot-1",
        nodeType: "Chatbot",
        field: "temperature",
        oldValue: 0.3,
        newValue: 0.5,
      },
    ];
    const onExpandField = jest.fn();
    render(<FlowDiffList entries={entries} onExpandField={onExpandField} />);
    const list = screen.getByTestId("version-diff-list");
    expect(list).toHaveTextContent("0.3");
    expect(list).toHaveTextContent("0.5");
    // Nothing to expand for a short value.
    expect(
      screen.queryByTestId("diff-expand-chatbot-1-temperature")
    ).not.toBeInTheDocument();
    expect(onExpandField).not.toHaveBeenCalled();
  });

  it("hands a long field change off to onExpandField instead of inlining it", () => {
    const longOld = "You are a helpful assistant.\nBe concise and accurate.";
    const longNew =
      "You are a helpful and friendly assistant.\nBe concise, accurate, and kind.";
    const entries: FlowDiffEntry[] = [
      {
        kind: "field-changed",
        nodeId: "chatbot-1",
        nodeType: "Chatbot",
        field: "system_prompt",
        oldValue: longOld,
        newValue: longNew,
      },
    ];
    const onExpandField = jest.fn();
    render(<FlowDiffList entries={entries} onExpandField={onExpandField} />);

    expect(screen.getByTestId("version-diff-list")).not.toHaveTextContent(
      longOld
    );
    fireEvent.click(screen.getByTestId("diff-expand-chatbot-1-system_prompt"));

    expect(onExpandField).toHaveBeenCalledWith({
      label: "Chatbot.system_prompt",
      oldValue: longOld,
      newValue: longNew,
    });
  });

  it("describes structural changes as added/removed nodes and connections", () => {
    const entries: FlowDiffEntry[] = [
      { kind: "node-added", nodeId: "n1", nodeType: "ChatOutput" },
      { kind: "node-removed", nodeId: "n2", nodeType: "OllamaModel" },
      {
        kind: "edge-added",
        edgeId: "e1",
        sourceNodeId: "n3",
        sourceType: "ChatInput",
        targetNodeId: "n1",
        targetType: "ChatOutput",
      },
    ];
    render(<FlowDiffList entries={entries} onExpandField={jest.fn()} />);
    const list = screen.getByTestId("version-diff-list");
    // node type names render as plain JSX children in edge rows (not
    // through an interpolated translation string), so those are asserted
    // directly; node-added/removed run their type through `t()` with
    // `{{type}}` interpolation, which this test setup's stripped-down
    // i18n (no I18nextProvider) doesn't substitute — see
    // react-i18next's `notReadyT` fallback.
    expect(list).toHaveTextContent("node added");
    expect(list).toHaveTextContent("node removed");
    expect(list).toHaveTextContent("ChatInput");
    expect(list).toHaveTextContent("ChatOutput");
  });
});
