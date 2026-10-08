import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import KnowledgeSearchView from "@/sections/knowledge-search/KnowledgeSearchView";
import {
  useDocumentChunks,
  useKnowledgeNeighborhoods,
  useKnowledgeSearch,
  useKnowledgeSearchSources,
} from "@/lib/api/domains/knowledge/hooks";
import { stubLifecycle } from "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub";
import {
  searchResponse,
  sources,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

// jsdom cannot draw on canvas; nodes become buttons named "name, label".
jest.mock("@/refresh-components/knowledge-graph/KnowledgeForceGraph", () =>
  jest.requireActual(
    "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub"
  )
);
jest.mock("@/lib/api/domains/knowledge/hooks", () => ({
  useKnowledgeSearch: jest.fn(),
  useKnowledgeSearchSources: jest.fn(),
  useKnowledgeNeighborhoods: jest.fn(),
  useDocumentChunks: jest.fn(),
}));
jest.mock("@/lib/api/domains/knowledge/api", () => ({
  fetchKnowledgeNeighborhood: jest.fn(),
}));
jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

beforeEach(() => {
  window.localStorage.clear();
  stubLifecycle.mounts = 0;
  jest.mocked(useKnowledgeSearch).mockImplementation((request) => ({
    result: request ? searchResponse({ query: request.query }) : undefined,
    error: undefined,
    isLoading: false,
    isValidating: false,
    isSearching: false,
    retry: jest.fn(),
  }));
  jest.mocked(useKnowledgeSearchSources).mockReturnValue({
    sources,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  });
  jest.mocked(useKnowledgeNeighborhoods).mockReturnValue({
    graphs: [],
    error: undefined,
    isLoading: false,
  });
  jest.mocked(useDocumentChunks).mockReturnValue({
    chunks: [],
    stats: null,
    isLoading: false,
    isLoadingMore: false,
    hasMore: false,
    loadMore: jest.fn(),
    error: undefined,
    mutate: jest.fn(),
  } as unknown as ReturnType<typeof useDocumentChunks>);
});

async function searchFor(query: string) {
  const user = userEvent.setup();
  await user.type(screen.getByRole("searchbox"), `${query}{Enter}`);
  return user;
}

describe("KnowledgeSearchView", () => {
  it("goes from the landing state to fused results", async () => {
    render(<KnowledgeSearchView />);

    expect(
      screen.getByRole("heading", { name: "Bilgi tabanında ara" })
    ).toBeInTheDocument();
    await searchFor("saklama");

    expect(screen.getByText("2 sonuç · 418 ms")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Arama özeti" })
    ).toBeInTheDocument();
  });

  it("opens a passage preview", async () => {
    render(<KnowledgeSearchView />);
    const user = await searchFor("saklama");

    await user.click(
      screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ })
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Sonuç önizlemesi",
    });

    expect(
      within(drawer).queryByRole("button", { name: "Sohbette sor" })
    ).not.toBeInTheDocument();
  });

  it("opens the graph view from the rail and previews an entity", async () => {
    render(<KnowledgeSearchView />);
    const user = await searchFor("saklama");

    await user.click(screen.getByRole("button", { name: "Graph'ta aç" }));
    expect(screen.getByRole("tab", { name: /Graph/ })).toHaveAttribute(
      "aria-selected",
      "true"
    );

    await user.click(
      screen.getByRole("button", { name: "Veri Koruma Sorumlusu, Role" })
    );
    const drawer = await screen.findByRole("dialog");
    expect(
      within(drawer).getByRole("heading", { name: "Veri Koruma Sorumlusu" })
    ).toBeInTheDocument();
  });

  it("keeps the graph mounted across searches", async () => {
    render(<KnowledgeSearchView />);
    const user = await searchFor("saklama");
    await user.click(screen.getByRole("button", { name: "Graph'ta aç" }));
    expect(stubLifecycle.mounts).toBe(1);

    await user.type(screen.getByRole("searchbox"), " süresi{Enter}");

    expect(screen.getByRole("tab", { name: /Graph/ })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    // The force graph refits itself for new data; a remount would drop the
    // canvas and restart its layout.
    expect(stubLifecycle.mounts).toBe(1);
  });

  it("shows the loading state until the new query answers", async () => {
    // The search hook withholds the previous query's response while the new
    // query is in flight.
    jest.mocked(useKnowledgeSearch).mockImplementation(() => ({
      result: undefined,
      error: undefined,
      isLoading: false,
      isValidating: true,
      isSearching: true,
      retry: jest.fn(),
    }));
    render(<KnowledgeSearchView />);

    await searchFor("saklama");

    expect(screen.getByRole("status")).toHaveTextContent("Aranıyor...");
    expect(
      screen.queryByRole("complementary", { name: "Arama özeti" })
    ).not.toBeInTheDocument();
    // The right column keeps its shape while the query is in flight, and stays
    // out of the accessibility tree so the search announces itself once.
    expect(
      screen.getByTestId("knowledge-search-rail-skeleton")
    ).toHaveAttribute("aria-hidden", "true");
  });

  it("returns to the landing state when the search is cleared", async () => {
    render(<KnowledgeSearchView />);
    const user = await searchFor("saklama");

    await user.click(screen.getByRole("button", { name: "Aramayı temizle" }));

    expect(
      screen.getByRole("heading", { name: "Bilgi tabanında ara" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "saklama" })).toBeInTheDocument();
  });

  it("fades each screen in when the view switches between landing and results", async () => {
    const { container } = render(<KnowledgeSearchView />);

    // The landing view is the screen that fades in first.
    expect(container.firstElementChild).toHaveClass("animate-in", "fade-in");

    await searchFor("saklama");

    // Switching screens replays the enter animation on the results screen.
    expect(container.firstElementChild).toHaveClass(
      "animate-in",
      "fade-in",
      "slide-in-from-bottom-1"
    );
  });

  it("spans the search box and filters over the whole panel width", async () => {
    render(<KnowledgeSearchView />);
    await searchFor("saklama");

    // The toolbar spans both grid columns, so the summary rail starts level
    // with the result list instead of hanging under an empty half-row.
    expect(screen.getByRole("search").parentElement).toHaveClass(
      "xl:col-span-2"
    );
  });
});
