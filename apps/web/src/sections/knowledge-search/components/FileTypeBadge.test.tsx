import { render, screen } from "@tests/setup/test-utils";

import FileTypeBadge from "@/sections/knowledge-search/components/FileTypeBadge";

describe("FileTypeBadge", () => {
  it("shows the type icon and tooltip instead of initials", () => {
    const { container } = render(<FileTypeBadge fileType="pdf" />);

    expect(screen.getByTitle("PDF").querySelector("svg")).toBeInTheDocument();
    expect(container).not.toHaveTextContent("PDF");
  });

  it("falls back to a neutral tile for an unknown type", () => {
    render(<FileTypeBadge fileType={null} />);

    const tile = screen.getByTitle("DOC");
    expect(tile.querySelector("svg")).toBeInTheDocument();
    expect(tile).toHaveClass("bg-background-tint-03");
  });

  it("draws a type emblem on the page grid, and only a page when unknown", () => {
    render(<FileTypeBadge fileType="pdf" />);
    const typed = screen.getByTitle("PDF").querySelector("svg");

    expect(typed).toHaveAttribute("viewBox", "0 0 16 20");
    expect(typed?.querySelector("rect")).toBeInTheDocument();

    render(<FileTypeBadge fileType="unknown-ext" />);
    const unknown = screen.getByTitle("UNKNOWN-EXT").querySelector("svg");

    expect(unknown?.querySelector("rect")).not.toBeInTheDocument();
  });
});
