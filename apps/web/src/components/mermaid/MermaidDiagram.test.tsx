import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { toast } from "@/hooks/useToast";
import { MermaidDiagram } from "@/components/mermaid/MermaidDiagram";
import { MermaidRenderError } from "@/components/mermaid/mermaidDiagnostics";

const mockRuntime = { peek: jest.fn(), render: jest.fn() };
jest.mock("@/components/mermaid/mermaidRuntime", () => ({
  getMermaidRuntime: () => mockRuntime,
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/components/mermaid/mermaidExport", () => ({
  ...jest.requireActual("@/components/mermaid/mermaidExport"),
  svgToPngBlob: jest.fn(() => Promise.reject(new Error("tainted canvas"))),
}));

const FLOW = "flowchart LR\n  A --> B";
const RESULT = {
  svg: '<svg id="mmd1z" viewBox="0 0 10 10"><marker id="mmd1z_arrow"></marker></svg>',
  renderId: "mmd1z",
};
const PARSE_ERROR = new MermaidRenderError({
  kind: "parse",
  message: "Expecting 'SEMI', got 'ARROW'",
  line: 3,
});

beforeEach(() => {
  mockRuntime.peek.mockReset().mockReturnValue(undefined);
  mockRuntime.render.mockReset().mockResolvedValue(RESULT);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: jest.fn().mockResolvedValue(undefined) },
  });
});

describe("MermaidDiagram", () => {
  it("uses the diagram title and description as the accessible name", async () => {
    mockRuntime.render.mockResolvedValue({
      svg: '<svg id="mmd1z" viewBox="0 0 10 10"><title>Orders</title><desc>Two steps</desc></svg>',
      renderId: "mmd1z",
    });
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    expect(
      await screen.findByRole("img", { name: "Orders. Two steps" })
    ).toBeInTheDocument();
  });

  it("sanitizes the injected svg (no foreignObject, scripts or handlers)", async () => {
    mockRuntime.render.mockResolvedValue({
      svg: '<svg id="mmd1z" viewBox="0 0 10 10"><foreignObject><div>x</div></foreignObject><script>alert(1)</script><rect onclick="alert(1)" width="1" height="1"></rect></svg>',
      renderId: "mmd1z",
    });
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    const host = await screen.findByTestId("mermaid-svg");
    expect(host.querySelector("foreignObject, script")).toBeNull();
    expect(host.querySelector("rect")?.hasAttribute("onclick")).toBe(false);
  });

  it("shows the writing skeleton and the type label, with no tools, while streaming", () => {
    renderWithI18n(
      <MermaidDiagram
        source={"sequenceDiagram\n  A->>B: Hi\n  B-->>A: Sel"}
        isComplete={false}
        variant="chat"
      />
    );

    expect(screen.getByText("mermaid · sequence diagram")).toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Writing diagram · 3 lines" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Copy code" })
    ).not.toBeInTheDocument();
    expect(mockRuntime.render).not.toHaveBeenCalled();
  });

  it("renders the svg under its own scope id with the full toolbar", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    const svg = await screen.findByTestId("mermaid-svg");
    expect(svg).toHaveAccessibleName("mermaid · flowchart");
    expect(svg.innerHTML).not.toContain("mmd1z");
    expect(svg.innerHTML).toMatch(/id="mmdv\d+z_arrow"/);
    for (const name of [
      "Copy code",
      "Download as SVG",
      "Download as PNG",
      "Expand",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.getByTestId("mermaid-diagram")).toHaveAttribute(
      "data-status",
      "rendered"
    );
  });

  it("toggles between diagram and code", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);
    await screen.findByTestId("mermaid-svg");

    fireEvent.click(screen.getByRole("button", { name: "Code" }));
    expect(screen.getByRole("button", { name: "Code" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByTestId("mermaid-source")).toHaveTextContent(
      "flowchart LR"
    );
    expect(screen.queryByTestId("mermaid-svg")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Diagram" }));
    expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument();
  });

  it("copies the source from the toolbar", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);
    await screen.findByTestId("mermaid-svg");

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));

    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(FLOW)
    );
  });

  it("shows the source with the failing line and hides the fix action without a handler", async () => {
    mockRuntime.render.mockReset().mockRejectedValue(PARSE_ERROR);
    const source = "flowchart LR\n  A --> B\n  B -->> C";
    const { container } = renderWithI18n(
      <MermaidDiagram source={source} isComplete variant="chat" />
    );

    expect(
      await screen.findByText(
        "Diagram could not be drawn · line 3: Expecting 'SEMI', got 'ARROW'"
      )
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-error-line="true"]')
    ).toHaveTextContent("B -->> C");
    expect(
      screen.queryByRole("button", { name: "Ask the agent to fix" })
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(source)
    );
    expect(toast.success).toHaveBeenCalledWith("Code copied");
  });

  it("hands the source and diagnostic to onRequestFix", async () => {
    mockRuntime.render.mockReset().mockRejectedValue(PARSE_ERROR);
    const onRequestFix = jest.fn();
    renderWithI18n(
      <MermaidDiagram
        source={FLOW}
        isComplete
        variant="chat"
        onRequestFix={onRequestFix}
      />
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "Ask the agent to fix" })
    );

    expect(onRequestFix).toHaveBeenCalledWith(FLOW, PARSE_ERROR.diagnostic);
  });

  it("keeps the last good svg with a notice when a new source fails", async () => {
    mockRuntime.render
      .mockReset()
      .mockResolvedValueOnce(RESULT)
      .mockRejectedValueOnce(PARSE_ERROR);
    const { rerender } = renderWithI18n(
      <MermaidDiagram source={FLOW} isComplete variant="document" />
    );
    await screen.findByTestId("mermaid-svg");

    rerender(
      <MermaidDiagram
        source={"flowchart LR\n  A BROKEN B"}
        isComplete
        variant="document"
      />
    );

    expect(await screen.findByTestId("mermaid-stale")).toHaveTextContent(
      "Showing the last version that could be drawn."
    );
    expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument();
    expect(screen.queryByText("mermaid · flowchart")).not.toBeInTheDocument();
  });

  it("downloads the svg copy", async () => {
    const createObjectURL = jest.fn((_blob: Blob) => "blob:mermaid");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: jest.fn(),
    });
    const click = jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Download as SVG" })
    );

    expect(createObjectURL.mock.calls[0]![0].type).toBe(
      "image/svg+xml;charset=utf-8"
    );
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it("reports a PNG export failure instead of throwing", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Download as PNG" })
    );

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "The diagram could not be exported."
      )
    );
  });

  it("opens the viewer", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);

    fireEvent.click(await screen.findByRole("button", { name: "Expand" }));

    expect(
      screen.getByRole("dialog", { name: "mermaid · flowchart" })
    ).toBeInTheDocument();
  });

  it("does not mount the viewer until Expand is clicked", async () => {
    renderWithI18n(<MermaidDiagram source={FLOW} isComplete variant="chat" />);
    await screen.findByTestId("mermaid-svg");

    expect(
      screen.queryByTestId("mermaid-viewer-canvas")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Expand" }));

    expect(screen.getByTestId("mermaid-viewer-canvas")).toBeInTheDocument();
  });

  it("uses the Turkish labels", async () => {
    renderWithI18n(
      <MermaidDiagram
        source={"sequenceDiagram\n  A->>B: Hi"}
        isComplete
        variant="chat"
      />,
      "tr"
    );

    // The label shows while pending; the tools appear only once the svg exists.
    expect(
      await screen.findByRole("button", { name: "Kod" })
    ).toBeInTheDocument();
    expect(screen.getByText("mermaid · sıra diyagramı")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Büyüt" })).toBeInTheDocument();
  });
});
