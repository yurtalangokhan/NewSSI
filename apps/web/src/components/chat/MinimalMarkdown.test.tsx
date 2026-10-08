import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import MinimalMarkdown from "./MinimalMarkdown";

describe("MinimalMarkdown", () => {
  describe("Link handling", () => {
    test("converts bare email markdown links to mailto links", () => {
      render(
        <MinimalMarkdown content="[support@anthropic.com](support@anthropic.com)" />
      );

      const link = screen.getByText("support@anthropic.com").closest("a");
      expect(link).toHaveAttribute("href", "mailto:support@anthropic.com");
    });

    test("preserves explicit mailto links", () => {
      render(
        <MinimalMarkdown content="[support@anthropic.com](mailto:support@anthropic.com)" />
      );

      const link = screen.getByText("support@anthropic.com").closest("a");
      expect(link).toHaveAttribute("href", "mailto:support@anthropic.com");
    });

    test("does not restore hrefs removed by url sanitization", () => {
      render(<MinimalMarkdown content="[click](javascript:alert(1))" />);

      const link = screen.getByText("click").closest("a");
      expect(link).not.toHaveAttribute("href");
    });
  });
});

// Uses the real runtime with the Jest mermaid double (tests/setup/mocks/mermaid.ts).
describe("MinimalMarkdown mermaid routing", () => {
  it("renders a closed mermaid fence as a document diagram", async () => {
    renderWithI18n(
      <MinimalMarkdown content={"```mermaid\nflowchart LR\n  A --> B\n```"} />
    );

    const svg = await screen.findByTestId("mermaid-svg");
    expect(svg.querySelector("svg")).not.toBeNull();
    expect(screen.getByTestId("mermaid-diagram")).toHaveAttribute(
      "data-variant",
      "document"
    );
  });

  it("highlights the line the renderer rejected", async () => {
    renderWithI18n(
      <MinimalMarkdown
        content={"```mermaid\nflowchart LR\n  A BROKEN B\n```"}
      />
    );

    const error = await screen.findByTestId("mermaid-error");
    expect(error.querySelector('[data-error-line="true"]')).toHaveTextContent(
      "A BROKEN B"
    );
  });

  it("keeps an open fence pending while streaming", () => {
    renderWithI18n(
      <MinimalMarkdown content={"```mermaid\nflowchart LR\n  A"} isStreaming />
    );

    expect(screen.getByTestId("mermaid-pending")).toBeInTheDocument();
  });

  it("still lets callers override code rendering", () => {
    renderWithI18n(
      <MinimalMarkdown
        content={"```mermaid\nflowchart LR\n```"}
        components={{ code: () => <span>custom</span> }}
      />
    );

    expect(screen.getByText("custom")).toBeInTheDocument();
    expect(screen.queryByTestId("mermaid-diagram")).not.toBeInTheDocument();
  });
});
