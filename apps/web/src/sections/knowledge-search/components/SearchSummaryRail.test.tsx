import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import SearchSummaryRail from "@/sections/knowledge-search/components/SearchSummaryRail";
import {
  searchGraph,
  searchResponse,
  sources,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);
jest.mock("@/refresh-components/knowledge-graph/KnowledgeForceGraph", () =>
  jest.requireActual(
    "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub"
  )
);

function renderRail(
  overrides: Partial<React.ComponentProps<typeof SearchSummaryRail>> = {}
) {
  const props: React.ComponentProps<typeof SearchSummaryRail> = {
    response: searchResponse({
      collections: [
        {
          id: "legal",
          name: "Hukuk & Sözleşmeler",
          documentHits: 9,
          entityHits: 0,
          status: "ok",
        },
        {
          id: "drive",
          name: "Satın Alma",
          documentHits: 3,
          entityHits: 0,
          status: "failed",
        },
        {
          id: "kg",
          name: "Kurumsal Graph",
          documentHits: 8,
          entityHits: 12,
          status: "ok",
        },
      ],
      facets: {
        fileTypes: [],
        entityLabels: [
          { value: "Policy", count: 2 },
          { value: "Role", count: 1 },
        ],
      },
    }),
    sources,
    graph: searchGraph,
    collectionIds: [],
    onCollectionsChange: jest.fn(),
    selectedEntityLabels: [],
    onEntityLabelToggle: jest.fn(),
    onOpenGraph: jest.fn(),
    ...overrides,
  };
  render(<SearchSummaryRail {...props} />);
  return props;
}

describe("SearchSummaryRail", () => {
  it("summarises results across collections", () => {
    renderRail();

    expect(screen.getByText("32 sonuç, 3 koleksiyon")).toBeInTheDocument();
    expect(screen.getByText("20 doküman parçası")).toBeInTheDocument();
    expect(screen.getByText("12 graph varlığı")).toBeInTheDocument();
  });

  it("lists collections with counts, source types, and status", () => {
    renderRail();

    const facet = screen.getByRole("group", { name: "Koleksiyonlar" });
    const all = within(facet).getByRole("button", { name: /Tüm kaynaklar/ });
    expect(all).toHaveAttribute("aria-pressed", "true");
    expect(all).toHaveTextContent("32");

    const drive = within(facet).getByRole("button", { name: /Satın Alma/ });
    expect(drive).toHaveTextContent("Connector");
    expect(drive).toHaveTextContent("Senkron");
    expect(drive).toHaveTextContent("Hata");
    expect(
      within(facet).getByRole("button", { name: /Kurumsal Graph/ })
    ).toHaveTextContent("Graph");
  });

  it("narrows to one collection and back to all sources", async () => {
    const user = userEvent.setup();
    const props = renderRail();

    await user.click(
      screen.getByRole("button", { name: /Hukuk & Sözleşmeler/ })
    );
    expect(props.onCollectionsChange).toHaveBeenLastCalledWith(["legal"]);

    await user.click(screen.getByRole("button", { name: /Tüm kaynaklar/ }));
    expect(props.onCollectionsChange).toHaveBeenLastCalledWith([]);
  });

  it("toggles a selected collection off", async () => {
    const user = userEvent.setup();
    const props = renderRail({ collectionIds: ["legal"] });

    const legal = screen.getByRole("button", { name: /Hukuk & Sözleşmeler/ });
    expect(legal).toHaveAttribute("aria-pressed", "true");
    await user.click(legal);

    expect(props.onCollectionsChange).toHaveBeenCalledWith([]);
  });

  it("previews the matched subgraph and opens the graph view", async () => {
    const user = userEvent.setup();
    const props = renderRail();

    expect(
      screen.getByRole("img", { name: "Sonuçların bilgi graph'ı" })
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Graph'ta aç" }));

    expect(props.onOpenGraph).toHaveBeenCalled();
  });

  it("hides the graph preview without entities", () => {
    renderRail({ graph: { nodes: [], edges: [] } });

    expect(screen.queryByText("Eşleşen alt graph")).not.toBeInTheDocument();
  });

  it("toggles entity type filters", async () => {
    const user = userEvent.setup();
    const props = renderRail({ selectedEntityLabels: ["Role"] });

    expect(screen.getByRole("button", { name: /Role/ })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await user.click(screen.getByRole("button", { name: /Policy/ }));

    expect(props.onEntityLabelToggle).toHaveBeenCalledWith("Policy");
  });

  it("hides collections that returned no hits", () => {
    renderRail({
      response: searchResponse({
        collections: [
          {
            id: "legal",
            name: "Hukuk & Sözleşmeler",
            documentHits: 9,
            entityHits: 0,
            status: "ok",
          },
          {
            id: "idle",
            name: "Boş Kaynak",
            documentHits: 0,
            entityHits: 0,
            status: "ok",
          },
        ],
        facets: { fileTypes: [], entityLabels: [] },
      }),
    });

    const facet = screen.getByRole("group", { name: "Koleksiyonlar" });
    expect(
      within(facet).queryByRole("button", { name: /Boş Kaynak/ })
    ).not.toBeInTheDocument();
    // The summary only counts the collections that are still listed.
    expect(screen.getByText("9 sonuç, 1 koleksiyon")).toBeInTheDocument();
  });
});
