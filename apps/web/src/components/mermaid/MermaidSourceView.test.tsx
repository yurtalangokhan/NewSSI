import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { MermaidSource } from "@/components/mermaid/MermaidSourceView";

describe("MermaidSource", () => {
  it("marks only the failing line", () => {
    const { container } = renderWithI18n(
      <MermaidSource
        source={"flowchart LR\n  A --> B\n  B -->> C"}
        highlightLine={3}
      />
    );

    const bad = container.querySelectorAll('[data-error-line="true"]');
    expect(bad).toHaveLength(1);
    expect(bad[0]).toHaveTextContent("B -->> C");
    expect(bad[0]).toHaveAttribute("data-line", "3");
  });

  it("keeps blank lines so line numbers stay aligned", () => {
    const { container } = renderWithI18n(<MermaidSource source={"a\n\nb"} />);

    expect(container.querySelectorAll("[data-line]")).toHaveLength(3);
  });
});
