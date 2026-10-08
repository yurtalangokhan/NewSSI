import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import ResultList from "@/sections/knowledge-search/components/ResultList";
import {
  documentHit,
  entityHit,
  searchResponse,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

function renderList(
  overrides: Partial<React.ComponentProps<typeof ResultList>> = {}
) {
  const props: React.ComponentProps<typeof ResultList> = {
    response: searchResponse(),
    error: undefined,
    isLoading: false,
    isSearching: false,
    query: "saklama",
    visibleCount: 10,
    limit: 50,
    selectedHitId: null,
    hasFilters: false,
    onOpen: jest.fn(),
    onShowMore: jest.fn(),
    onRetry: jest.fn(),
    onResetFilters: jest.fn(),
    ...overrides,
  };
  render(<ResultList {...props} />);
  return props;
}

describe("ResultList", () => {
  it("renders document and entity cards with kind tags in hybrid search", async () => {
    const user = userEvent.setup();
    const props = renderList();

    expect(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    ).toHaveTextContent("Parça");
    const entity = screen.getByRole("button", {
      name: /Veri Saklama Politikası/,
    });
    expect(entity).toHaveTextContent("Varlık");

    await user.click(entity);
    expect(props.onOpen).toHaveBeenCalledWith(entityHit);
  });

  it("omits kind tags outside hybrid search", () => {
    renderList({
      response: searchResponse({ kind: "vector", hits: [documentHit] }),
    });

    expect(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    ).not.toHaveTextContent("Parça");
  });

  it("offers to show the remaining results", async () => {
    const user = userEvent.setup();
    const hits = Array.from({ length: 12 }, (_, index) => ({
      ...documentHit,
      id: `c${index}`,
    }));
    const props = renderList({
      response: searchResponse({ hits, total: 12 }),
    });

    expect(screen.getAllByRole("button", { name: /Tedarikçi/ })).toHaveLength(
      10
    );
    await user.click(
      screen.getByRole("button", { name: "2 sonuç daha göster" })
    );
    expect(props.onShowMore).toHaveBeenCalled();
  });

  it("hides show more when everything is visible", () => {
    renderList();

    expect(
      screen.queryByRole("button", { name: /sonuç daha göster/ })
    ).not.toBeInTheDocument();
  });

  it("shows skeletons while the first search loads", () => {
    renderList({ response: undefined, isLoading: true });

    expect(screen.getByRole("status")).toHaveTextContent("Aranıyor...");
  });

  it("shows skeletons while a query waits for its response", () => {
    renderList({ response: undefined, isLoading: false, isSearching: true });

    expect(screen.getByRole("status")).toHaveTextContent("Aranıyor...");
  });

  it("keeps the hits visible and dims the list while a search refreshes", () => {
    renderList({ isSearching: true });

    expect(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    ).toBeInTheDocument();
    expect(screen.getByRole("list")).toHaveClass("opacity-60");
  });

  it("shows a retryable error", async () => {
    const user = userEvent.setup();
    const props = renderList({
      response: undefined,
      error: new Error("Graph search permission is required."),
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Arama başarısız oldu");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Graph search permission is required."
    );
    await user.click(screen.getByRole("button", { name: "Tekrar dene" }));
    expect(props.onRetry).toHaveBeenCalled();
  });

  it("explains empty results", () => {
    renderList({ response: searchResponse({ hits: [], total: 0 }) });

    expect(screen.getByText("Sonuç bulunamadı")).toBeInTheDocument();
  });

  it("offers to reset filters when filters hide every result", async () => {
    const user = userEvent.setup();
    const props = renderList({
      response: searchResponse({ hits: [], total: 0 }),
      hasFilters: true,
    });

    expect(
      screen.getByText("Bu filtrelere uyan sonuç yok.")
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Filtreleri sıfırla" })
    );
    expect(props.onResetFilters).toHaveBeenCalled();
  });

  it("warns about failed collections and hidden graph results", () => {
    renderList({
      response: searchResponse({
        graphAvailable: false,
        collections: [
          {
            id: "legal",
            name: "Hukuk",
            documentHits: 0,
            entityHits: 0,
            status: "failed",
          },
        ],
      }),
    });

    expect(screen.getByText("1 koleksiyon aranamadı.")).toBeInTheDocument();
    expect(
      screen.getByText(/Graph arama yetkiniz olmadığı için/)
    ).toBeInTheDocument();
  });

  it("tells a graph store outage apart from a missing graph permission", () => {
    renderList({
      response: searchResponse({
        graphAvailable: false,
        graphUnavailable: true,
      }),
    });

    expect(
      screen.getByText(/Graph deposuna şu anda ulaşılamıyor/)
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Graph arama yetkiniz olmadığı için/)
    ).not.toBeInTheDocument();
  });

  it("shows no graph notice when the graph is available", () => {
    renderList({ response: searchResponse() });

    expect(
      screen.queryByText(/Graph arama yetkiniz olmadığı için/)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Graph deposuna şu anda ulaşılamıyor/)
    ).not.toBeInTheDocument();
  });

  it("marks the selected card", () => {
    renderList({ selectedHitId: "c1" });

    expect(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    ).toHaveAttribute("data-selected", "true");
  });
});
