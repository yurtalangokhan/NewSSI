import { act, render } from "@testing-library/react";
import { DocumentPreviewPlaceholder } from "@/sections/document-panel/DocumentPreviewPlaceholder";
import { setWhitePageMode } from "@/sections/document-panel/useWhitePage";

afterEach(() => {
  act(() => setWhitePageMode("off"));
});

it("follows the white page modes while a document loads", () => {
  const { container, rerender } = render(<DocumentPreviewPlaceholder />);
  expect(container.querySelector(".theme-light")).toBeNull();
  expect(
    container.querySelector("[data-testid='document-preview-skeleton']")
  ).not.toBeNull();

  // `paper`: a light sheet inside the app surface.
  act(() => setWhitePageMode("paper"));
  rerender(<DocumentPreviewPlaceholder />);
  const sheet = container.querySelector(".theme-light");
  expect(sheet).toHaveClass("rounded-12");

  // `page`: the reading area itself is the page, so the skeleton is drawn on it
  // without a second sheet.
  act(() => setWhitePageMode("page"));
  rerender(<DocumentPreviewPlaceholder />);
  const surfaces = container.querySelectorAll(".theme-light");
  expect(surfaces).toHaveLength(1);
  expect(surfaces[0]).toHaveClass("bg-background-tint-00");
  expect(surfaces[0]).not.toHaveClass("rounded-12");
});
