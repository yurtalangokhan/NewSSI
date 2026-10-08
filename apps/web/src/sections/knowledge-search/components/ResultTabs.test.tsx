import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import ResultTabs from "@/sections/knowledge-search/components/ResultTabs";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

describe("ResultTabs", () => {
  it("shows result and node counts and switches tabs", async () => {
    const user = userEvent.setup();
    const onTabChange = jest.fn();
    render(
      <ResultTabs
        tab="list"
        onTabChange={onTabChange}
        resultCount={32}
        nodeCount={14}
        listPanel={<p>liste içeriği</p>}
        graphPanel={<p>graph içeriği</p>}
      />
    );

    expect(screen.getByRole("tab", { name: /Liste/ })).toHaveTextContent("32");
    expect(screen.getByRole("tab", { name: /Graph/ })).toHaveTextContent(
      "14 düğüm"
    );
    expect(screen.getByText("liste içeriği")).toBeInTheDocument();
    expect(screen.queryByText("graph içeriği")).not.toBeInTheDocument();
    expect(screen.getByText("Alaka düzeyine göre")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Graph/ }));
    expect(onTabChange).toHaveBeenCalledWith("graph");
  });

  it("stretches the active panel over the column instead of shrink-wrapping it", () => {
    render(
      <ResultTabs
        tab="list"
        onTabChange={jest.fn()}
        resultCount={32}
        nodeCount={0}
        listPanel={<p>liste içeriği</p>}
        graphPanel={<p>graph içeriği</p>}
      />
    );

    // Tabs.Content's Section centres and shrink-wraps by default, which let
    // long result rows spill over the summary rail.
    const panel = screen.getByText("liste içeriği").parentElement;
    expect(panel).toHaveClass("items-stretch");
    expect(panel).toHaveClass("justify-start");
  });

  it("renders the graph panel when the graph tab is active", () => {
    render(
      <ResultTabs
        tab="graph"
        onTabChange={jest.fn()}
        resultCount={0}
        nodeCount={1}
        listPanel={<p>liste içeriği</p>}
        graphPanel={<p>graph içeriği</p>}
      />
    );

    expect(screen.getByText("graph içeriği")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Graph/ })).toHaveTextContent(
      "1 düğüm"
    );
  });
});
