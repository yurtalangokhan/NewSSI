import { fireEvent, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { MermaidErrorView } from "@/components/mermaid/MermaidErrorView";

const SOURCE = "flowchart LR\n  A --> B\n  B -->> C";
const MESSAGE = "Diagram could not be drawn · line 3: Expecting 'SEMI'";

describe("MermaidErrorView", () => {
  it("shows the message, highlights the line and offers both actions", () => {
    const onCopy = jest.fn();
    const onRequestFix = jest.fn();
    const { container } = renderWithI18n(
      <MermaidErrorView
        source={SOURCE}
        message={MESSAGE}
        highlightLine={3}
        onCopy={onCopy}
        onRequestFix={onRequestFix}
      />
    );

    expect(screen.getByText(MESSAGE)).toBeInTheDocument();
    // The banner is announced, not just coloured.
    expect(screen.getByRole("alert")).toHaveTextContent(MESSAGE);
    expect(
      container.querySelector('[data-error-line="true"]')
    ).toHaveTextContent("B -->> C");
    fireEvent.click(
      screen.getByRole("button", { name: "Ask the agent to fix" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    expect(onRequestFix).toHaveBeenCalledTimes(1);
    expect(onCopy).toHaveBeenCalledTimes(1);
  });

  it("hides the fix action when no handler is given", () => {
    renderWithI18n(
      <MermaidErrorView
        source={SOURCE}
        message={MESSAGE}
        highlightLine={3}
        onCopy={jest.fn()}
      />
    );

    expect(
      screen.queryByRole("button", { name: "Ask the agent to fix" })
    ).not.toBeInTheDocument();
  });

  it("uses the Turkish labels from the approved design", () => {
    renderWithI18n(
      <MermaidErrorView
        source={SOURCE}
        message={MESSAGE}
        highlightLine={3}
        onCopy={jest.fn()}
        onRequestFix={jest.fn()}
      />,
      "tr"
    );

    expect(
      screen.getByRole("button", { name: "Ajana düzelttir" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Kodu kopyala" })
    ).toBeInTheDocument();
  });
});
