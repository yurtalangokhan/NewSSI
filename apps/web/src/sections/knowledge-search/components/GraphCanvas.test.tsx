import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import GraphCanvas from "@/sections/knowledge-search/components/GraphCanvas";
import { stubCamera as camera } from "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub";
import { searchGraph } from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);
jest.mock("@/refresh-components/knowledge-graph/KnowledgeForceGraph", () =>
  jest.requireActual(
    "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub"
  )
);

function renderCanvas(
  overrides: Partial<React.ComponentProps<typeof GraphCanvas>> = {}
) {
  const props: React.ComponentProps<typeof GraphCanvas> = {
    graph: searchGraph,
    selectedNodeId: null,
    onSelectNode: jest.fn(),
    depth: 1,
    onDepthChange: jest.fn(),
    matchedOnly: false,
    onMatchedOnlyToggle: jest.fn(),
    isExpanding: false,
    canExpand: true,
    ...overrides,
  };
  render(<GraphCanvas {...props} />);
  return props;
}

beforeEach(() => {
  camera.zoomBy.mockClear();
  camera.fit.mockClear();
});

describe("GraphCanvas", () => {
  it("drives the graph camera from the zoom controls", async () => {
    const user = userEvent.setup();
    renderCanvas();

    await user.click(screen.getByRole("button", { name: "Yakınlaştır" }));
    expect(camera.zoomBy).toHaveBeenLastCalledWith(1.25);
    await user.click(screen.getByRole("button", { name: "Uzaklaştır" }));
    expect(camera.zoomBy).toHaveBeenLastCalledWith(0.8);
    await user.click(screen.getByRole("button", { name: "Sığdır" }));
    expect(camera.fit).toHaveBeenCalledTimes(1);
  });

  it("changes depth and matched-only mode", async () => {
    const user = userEvent.setup();
    const props = renderCanvas();

    await user.click(screen.getByRole("button", { name: "Derinlik: 1" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: /2 adım/,
      })
    );
    expect(props.onDepthChange).toHaveBeenCalledWith(2);

    const matchedOnly = screen.getByRole("button", {
      name: "Yalnızca eşleşenler",
    });
    expect(matchedOnly).toHaveAttribute("aria-pressed", "false");
    await user.click(matchedOnly);
    expect(props.onMatchedOnlyToggle).toHaveBeenCalled();
  });

  it("disables depth without graph read permission", () => {
    renderCanvas({ canExpand: false });

    expect(screen.getByRole("button", { name: "Derinlik: 1" })).toBeDisabled();
  });

  it("selects nodes from the drawing and the relation list", async () => {
    const user = userEvent.setup();
    const props = renderCanvas({ selectedNodeId: "n1" });

    await user.click(
      screen.getByRole("button", { name: "Veri Koruma Sorumlusu, Role" })
    );
    expect(props.onSelectNode).toHaveBeenCalledWith(searchGraph.nodes[1]);

    const relations = screen.getByRole("list", { name: "İlişkiler" });
    await user.click(
      within(relations).getByRole("button", { name: /SORUMLUSU/ })
    );
    expect(props.onSelectNode).toHaveBeenLastCalledWith(searchGraph.nodes[0]);
  });

  it("shows the legend of entity types", () => {
    renderCanvas();

    const legend = screen.getByTestId("knowledge-graph-legend");
    expect(legend).toHaveTextContent("Policy");
    expect(legend).toHaveTextContent("Role");
    expect(legend).toHaveTextContent(
      "Dolu düğüm: sorguyla eşleşti · Halka: komşu"
    );
  });

  it("reports neighbor expansion in progress", () => {
    renderCanvas({ isExpanding: true });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Komşular yükleniyor..."
    );
  });

  it("explains an empty graph", () => {
    renderCanvas({ graph: { nodes: [], edges: [] } });

    expect(
      screen.getByText("Bu aramada graph varlığı yok.")
    ).toBeInTheDocument();
  });
});
