import { render, screen } from "@testing-library/react";
import { DocumentContentView } from "@/sections/document-panel/DocumentContentView";
import { documentUrlTransform } from "@/sections/document-panel/attachmentImages";

describe("documentUrlTransform", () => {
  it("points an attachment reference at the chat file endpoint", () => {
    expect(documentUrlTransform("attachment:abc-123")).toBe(
      "/api/chat/file/abc-123"
    );
  });

  it("refuses an attachment id that is not a plain file id", () => {
    expect(documentUrlTransform("attachment:../../secret")).toBeNull();
    expect(documentUrlTransform("attachment:")).toBeNull();
  });

  it("keeps the shared link rules for everything else", () => {
    expect(documentUrlTransform("https://example.com/a.png")).toBe(
      "https://example.com/a.png"
    );
    expect(documentUrlTransform("javascript:alert(1)")).toBeNull();
  });
});

describe("DocumentContentView attachment images", () => {
  it("renders an attached image through the chat file endpoint", () => {
    render(
      <DocumentContentView markdown={"![Sales chart](attachment:file-1)"} />
    );

    expect(screen.getByAltText("Sales chart")).toHaveAttribute(
      "src",
      "/api/chat/file/file-1"
    );
  });

  it("still drops an image with a script scheme", () => {
    render(<DocumentContentView markdown={"![x](javascript:alert(1))"} />);

    expect(screen.queryByAltText("x")?.getAttribute("src") ?? "").toBe("");
  });
});
