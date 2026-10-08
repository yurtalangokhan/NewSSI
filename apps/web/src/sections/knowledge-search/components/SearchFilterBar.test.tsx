import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import SearchFilterBar from "@/sections/knowledge-search/components/SearchFilterBar";
import type { KnowledgeSearchSource } from "@/lib/api/domains/knowledge/knowledge-search-types";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

const SOURCES: KnowledgeSearchSource[] = [
  {
    id: "legal",
    name: "Hukuk",
    sourceType: "document",
    connectorType: "",
    syncStatus: "idle",
    hasGraph: false,
  },
  {
    id: "kg",
    name: "Kurumsal Graph",
    sourceType: "document",
    connectorType: "",
    syncStatus: "idle",
    hasGraph: true,
  },
];

function renderBar(
  overrides: Partial<React.ComponentProps<typeof SearchFilterBar>> = {}
) {
  const props: React.ComponentProps<typeof SearchFilterBar> = {
    sources: SOURCES,
    collectionIds: [],
    onCollectionToggle: jest.fn(),
    onCollectionsClear: jest.fn(),
    fileTypes: [
      { value: "pdf", count: 3 },
      { value: "docx", count: 1 },
    ],
    selectedFileTypes: [],
    onFileTypeToggle: jest.fn(),
    onFileTypesClear: jest.fn(),
    entityLabels: [{ value: "Policy", count: 2 }],
    selectedEntityLabels: [],
    onEntityLabelToggle: jest.fn(),
    onEntityLabelsClear: jest.fn(),
    limit: 50,
    onLimitChange: jest.fn(),
    total: 32,
    elapsedMs: 418,
    ...overrides,
  };
  render(<SearchFilterBar {...props} />);
  return props;
}

describe("SearchFilterBar", () => {
  it("shows the result count and search time", () => {
    renderBar();

    expect(screen.getByText("32 sonuç · 418 ms")).toBeInTheDocument();
  });

  it("toggles collections from the collection filter", async () => {
    const user = userEvent.setup();
    const props = renderBar({ collectionIds: ["legal"] });

    await user.click(screen.getByRole("button", { name: /Hukuk/ }));
    const menu = await screen.findByRole("dialog");
    await user.click(
      within(menu).getByRole("button", { name: /Kurumsal Graph/ })
    );

    expect(props.onCollectionToggle).toHaveBeenCalledWith("kg");
  });

  it("filters the collection list by name", async () => {
    const user = userEvent.setup();
    renderBar();

    await user.click(screen.getByRole("button", { name: /Koleksiyon/ }));
    const menu = await screen.findByRole("dialog");
    await user.type(
      within(menu).getByPlaceholderText("Koleksiyonları filtrele..."),
      "graph"
    );

    expect(
      within(menu).queryByRole("button", { name: /Hukuk/ })
    ).not.toBeInTheDocument();
    expect(
      within(menu).getByRole("button", { name: /Kurumsal Graph/ })
    ).toBeInTheDocument();
  });

  it("clears the collection filter", async () => {
    const user = userEvent.setup();
    const props = renderBar({ collectionIds: ["legal", "kg"] });

    const button = screen.getByRole("button", { name: /Koleksiyon: 2/ });
    await user.click(
      within(button).getByRole("button", { name: "Clear filter" })
    );

    expect(props.onCollectionsClear).toHaveBeenCalledTimes(1);
  });

  it("toggles file types with their counts", async () => {
    const user = userEvent.setup();
    const props = renderBar();

    await user.click(screen.getByRole("button", { name: /Dosya türü/ }));
    const menu = await screen.findByRole("dialog");
    const pdf = within(menu).getByRole("button", { name: /PDF/ });
    expect(pdf).toHaveTextContent("3");
    await user.click(pdf);

    expect(props.onFileTypeToggle).toHaveBeenCalledWith("pdf");
  });

  it("clears file types and entity labels", async () => {
    const user = userEvent.setup();
    const props = renderBar({
      selectedFileTypes: ["pdf"],
      selectedEntityLabels: ["Policy"],
    });

    await user.click(
      within(screen.getByRole("button", { name: /PDF/ })).getByRole("button", {
        name: "Clear filter",
      })
    );
    await user.click(
      within(screen.getByRole("button", { name: /Policy/ })).getByRole(
        "button",
        { name: "Clear filter" }
      )
    );

    expect(props.onFileTypesClear).toHaveBeenCalled();
    expect(props.onEntityLabelsClear).toHaveBeenCalled();
  });

  it("toggles entity labels", async () => {
    const user = userEvent.setup();
    const props = renderBar();

    await user.click(screen.getByRole("button", { name: /Varlık türü/ }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: /Policy/,
      })
    );

    expect(props.onEntityLabelToggle).toHaveBeenCalledWith("Policy");
  });

  it("explains empty facets", async () => {
    const user = userEvent.setup();
    renderBar({ fileTypes: [] });

    await user.click(screen.getByRole("button", { name: /Dosya türü/ }));

    expect(
      within(await screen.findByRole("dialog")).getByText(
        "Henüz filtrelenecek bir şey yok"
      )
    ).toBeInTheDocument();
  });

  it("changes the result limit from the settings", async () => {
    const user = userEvent.setup();
    const props = renderBar();

    await user.click(screen.getByRole("button", { name: "Arama ayarları" }));
    const menu = await screen.findByRole("dialog");
    await user.click(within(menu).getByRole("button", { name: /100 sonuç/ }));

    expect(props.onLimitChange).toHaveBeenCalledWith(100);
  });

  it("hides the meta line before results arrive", () => {
    renderBar({ total: undefined, elapsedMs: undefined });

    expect(screen.queryByText(/sonuç ·/)).not.toBeInTheDocument();
  });

  it("replaces the meta line with progress while a search refreshes", () => {
    renderBar({ isSearching: true });

    expect(screen.getByText("Aranıyor...")).toBeInTheDocument();
    expect(screen.queryByText("32 sonuç · 418 ms")).not.toBeInTheDocument();
  });
});
