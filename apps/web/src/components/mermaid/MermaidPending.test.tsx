import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { MermaidPending } from "@/components/mermaid/MermaidPending";

describe("MermaidPending", () => {
  it("shows the streamed line count and the last streamed line", () => {
    renderWithI18n(
      <MermaidPending
        source={"sequenceDiagram\n  E->>H: Sözleşme kontr"}
        isComplete={false}
      />,
      "tr"
    );

    expect(
      screen.getByRole("status", { name: "Diyagram yazılıyor · 2 satır" })
    ).toBeInTheDocument();
    expect(screen.getByTestId("mermaid-pending-tail")).toHaveTextContent(
      "E->>H: Sözleşme kontr"
    );
  });

  it("uses the singular in English", () => {
    renderWithI18n(<MermaidPending source="flowchart LR" isComplete={false} />);

    expect(
      screen.getByRole("status", { name: "Writing diagram · 1 line" })
    ).toBeInTheDocument();
  });

  it("switches to the drawing state without a tail once the fence is closed", () => {
    renderWithI18n(
      <MermaidPending source={"flowchart LR\n  A --> B"} isComplete />
    );

    expect(
      screen.getByRole("status", { name: "Drawing diagram…" })
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("mermaid-pending-tail")
    ).not.toBeInTheDocument();
  });
});
