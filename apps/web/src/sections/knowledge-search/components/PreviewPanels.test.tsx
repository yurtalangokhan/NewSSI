import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import DocumentPreview from "@/sections/knowledge-search/components/DocumentPreview";
import EntityPreview from "@/sections/knowledge-search/components/EntityPreview";
import SearchPreviewDrawer from "@/sections/knowledge-search/components/SearchPreviewDrawer";
import {
  documentHit,
  entityHit,
  searchGraph,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";
import { useDocumentChunks } from "@/lib/api/domains/knowledge/hooks";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

jest.mock("@/lib/api/domains/knowledge/hooks", () => ({
  useDocumentChunks: jest.fn(),
}));

const chunksHook = jest.mocked(useDocumentChunks);

function chunksState(overrides: Partial<ReturnType<typeof useDocumentChunks>>) {
  return {
    chunks: [],
    stats: null,
    isLoading: false,
    isLoadingMore: false,
    hasMore: false,
    loadMore: jest.fn(),
    error: undefined,
    mutate: jest.fn(),
    ...overrides,
  } as ReturnType<typeof useDocumentChunks>;
}

const CHUNKS = [
  { id: "c0", content: "Önceki madde: alt işleyici bildirimi." },
  { id: "c1", content: documentHit.document!.content },
  { id: "c2", content: "Sonraki madde: imha tutanağı." },
];

describe("SearchPreviewDrawer", () => {
  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    render(
      <SearchPreviewDrawer open onClose={onClose}>
        <p>içerik</p>
      </SearchPreviewDrawer>
    );

    expect(
      screen.getByRole("dialog", { name: "Sonuç önizlemesi" })
    ).toHaveTextContent("içerik");
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("DocumentPreview", () => {
  beforeEach(() => {
    chunksHook.mockReturnValue(
      chunksState({
        chunks: CHUNKS,
        stats: { total_chunks: 3, avg_chars: 50, avg_tokens: 12 },
      })
    );
  });

  it("shows the matched passage, its position, and surrounding passages", () => {
    render(
      <DocumentPreview hit={documentHit} query="saklama" onClose={jest.fn()} />
    );

    expect(chunksHook).toHaveBeenCalledWith("legal", "f-1");
    expect(
      screen.getByRole("heading", { name: "Tedarikçi Sözleşmesi" })
    ).toBeInTheDocument();
    const matched = screen.getByTestId("matched-passage");
    expect(matched).toHaveTextContent("Parça 2 / 3");
    expect(within(matched).getByText("saklama").tagName).toBe("MARK");
    expect(screen.getByText(CHUNKS[0]!.content)).toBeInTheDocument();
    expect(screen.getByText(CHUNKS[2]!.content)).toBeInTheDocument();
    expect(screen.getByText("token_count")).toBeInTheDocument();
  });

  it("shows the full document and loads more passages", async () => {
    const user = userEvent.setup();
    const loadMore = jest.fn();
    chunksHook.mockReturnValue(
      chunksState({ chunks: CHUNKS, hasMore: true, loadMore })
    );
    render(
      <DocumentPreview hit={documentHit} query="saklama" onClose={jest.fn()} />
    );

    await user.click(
      screen.getByRole("button", { name: "Tüm dokümanı göster" })
    );
    const full = screen.getByRole("list", { name: "Dokümanın tamamı" });
    expect(within(full).getAllByRole("listitem")).toHaveLength(3);
    expect(within(full).getAllByRole("listitem")[1]).toHaveAttribute(
      "aria-current",
      "true"
    );

    await user.click(
      screen.getByRole("button", { name: "Daha fazla parça yükle" })
    );
    expect(loadMore).toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: "Tüm dokümanı gizle" })
    );
    expect(
      screen.queryByRole("list", { name: "Dokümanın tamamı" })
    ).not.toBeInTheDocument();
  });

  it("loads further pages until the matched passage is found", () => {
    const loadMore = jest.fn();
    chunksHook.mockReturnValue(
      chunksState({ chunks: [CHUNKS[0]!], hasMore: true, loadMore })
    );

    render(<DocumentPreview hit={documentHit} query="q" onClose={jest.fn()} />);

    expect(loadMore).toHaveBeenCalled();
  });

  it("skips document passages for rows without a file id", () => {
    chunksHook.mockReturnValue(chunksState({}));
    render(
      <DocumentPreview
        hit={{
          ...documentHit,
          document: { ...documentHit.document!, fileId: null },
        }}
        query="q"
        onClose={jest.fn()}
      />
    );

    expect(chunksHook).toHaveBeenCalledWith("legal", null);
    expect(
      screen.queryByRole("button", { name: "Tüm dokümanı göster" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Çevresindeki parçalar")).not.toBeInTheDocument();
  });

  it("reports chunk loading errors", () => {
    chunksHook.mockReturnValue(chunksState({ error: new Error("down") }));
    render(<DocumentPreview hit={documentHit} query="q" onClose={jest.fn()} />);

    expect(screen.getByText("Parçalar yüklenemedi.")).toBeInTheDocument();
  });

  it("closes from the header", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    render(<DocumentPreview hit={documentHit} query="q" onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "Kapat" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("EntityPreview", () => {
  function renderEntity(
    overrides: Partial<React.ComponentProps<typeof EntityPreview>> = {}
  ) {
    const props: React.ComponentProps<typeof EntityPreview> = {
      node: searchGraph.nodes[0]!,
      hit: entityHit,
      graph: searchGraph,
      collectionName: "Kurumsal Graph",
      expansionDepth: 0,
      onExpand: jest.fn(),
      isExpanding: false,
      canExpand: true,
      onSelectNode: jest.fn(),
      onClose: jest.fn(),
      ...overrides,
    };
    render(<EntityPreview {...props} />);
    return props;
  }

  function renderExpanded(expansionDepth: number) {
    return render(
      <EntityPreview
        node={searchGraph.nodes[0]!}
        hit={entityHit}
        graph={searchGraph}
        collectionName="Kurumsal Graph"
        onExpand={jest.fn()}
        isExpanding={false}
        expansionDepth={expansionDepth}
        canExpand
        onSelectNode={jest.fn()}
        onClose={jest.fn()}
      />
    );
  }

  it("shows the entity with its neighborhood, relations, and properties", () => {
    renderEntity();

    expect(
      screen.getByRole("heading", { name: "Veri Saklama Politikası" })
    ).toBeInTheDocument();
    expect(screen.getByText("Eşleşti")).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Yakın çevre" })
    ).toBeInTheDocument();
    expect(screen.getByText("İlişkiler · 1")).toBeInTheDocument();
    expect(screen.getByText("sürüm")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
  });

  it("navigates to a related entity", async () => {
    const user = userEvent.setup();
    const props = renderEntity();

    const relations = screen.getByRole("list", { name: "İlişkiler · 1" });
    await user.click(
      within(relations).getByRole("button", { name: /Veri Koruma Sorumlusu/ })
    );

    expect(props.onSelectNode).toHaveBeenCalledWith(searchGraph.nodes[1]);
  });

  it("expands neighbors", async () => {
    const user = userEvent.setup();
    const props = renderEntity();

    await user.click(
      screen.getByRole("button", { name: "Komşuları genişlet" })
    );
    expect(props.onExpand).toHaveBeenCalledWith(searchGraph.nodes[0]);
  });

  it("offers to expand deeper, then reports everything loaded", () => {
    const { unmount } = renderExpanded(1);
    expect(
      screen.getByRole("button", { name: "Daha derine genişlet" })
    ).toBeEnabled();
    unmount();

    renderExpanded(3);
    expect(
      screen.getByRole("button", { name: "Tüm komşular yüklendi" })
    ).toBeDisabled();
  });

  it("labels neighbors and shows expansion progress", () => {
    renderEntity({
      node: searchGraph.nodes[1]!,
      hit: undefined,
      isExpanding: true,
    });

    expect(screen.getByText("Komşu")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Genişletiliyor..." })
    ).toBeDisabled();
  });

  it("disables expansion without graph read permission", () => {
    renderEntity({ canExpand: false });

    expect(
      screen.getByRole("button", { name: "Komşuları genişlet" })
    ).toBeDisabled();
  });

  it("explains an entity without relationships", () => {
    renderEntity({
      graph: { nodes: [searchGraph.nodes[0]!], edges: [] },
    });

    expect(screen.getByText("İlişki bulunamadı.")).toBeInTheDocument();
  });
});
