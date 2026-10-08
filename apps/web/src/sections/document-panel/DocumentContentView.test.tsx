import { act, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentContentView } from "@/sections/document-panel/DocumentContentView";
import { setWhitePageMode } from "@/sections/document-panel/useWhitePage";

afterEach(() => {
  act(() => setWhitePageMode("off"));
});

function paper() {
  return screen.getByTestId("document-content");
}

it("keeps the paper on the app surface by default", () => {
  renderWithI18n(<DocumentContentView markdown="# Başlık" />);

  expect(paper()).not.toHaveClass("theme-light");
  expect(paper().querySelector(".prose")).toHaveClass("dark:prose-invert");
});

it.each(["paper", "page"] as const)(
  "renders a light sheet in `%s` mode",
  (mode) => {
    act(() => setWhitePageMode(mode));
    renderWithI18n(<DocumentContentView markdown="# Başlık" />);

    // `.theme-light` re-applies the light tokens, so the sheet stays white with
    // dark text even in dark mode.
    expect(paper()).toHaveClass("theme-light");
    // The class-based `dark:prose-invert` would paint light text on the sheet.
    expect(paper().querySelector(".prose")).not.toHaveClass(
      "dark:prose-invert"
    );
  }
);
