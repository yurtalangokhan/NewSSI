import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import KnowledgeGraphSvg from "@/sections/knowledge-search/components/KnowledgeGraphSvg";
import { searchGraph } from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

describe("KnowledgeGraphSvg", () => {
  it("draws matched nodes filled and neighbors as rings, with their edge", () => {
    render(
      <KnowledgeGraphSvg
        graph={searchGraph}
        width={600}
        height={400}
        labels="all"
        ariaLabel="graph"
      />
    );

    const nodes = screen.getAllByTestId("knowledge-search-node");
    expect(nodes.map((node) => node.getAttribute("data-matched"))).toEqual([
      "true",
      "false",
    ]);
    expect(screen.getByText("Veri Saklama Politikası")).toBeInTheDocument();
    expect(screen.getByText("Veri Koruma Sorumlusu")).toBeInTheDocument();
    expect(screen.getAllByTestId("knowledge-search-edge")).toHaveLength(1);
  });

  it("labels only matched nodes in compact mode", () => {
    render(
      <KnowledgeGraphSvg
        graph={searchGraph}
        width={600}
        height={400}
        labels="matched"
        ariaLabel="graph"
      />
    );

    expect(screen.getByText("Veri Saklama Politikası")).toBeInTheDocument();
    expect(screen.queryByText("Veri Koruma Sorumlusu")).not.toBeInTheDocument();
  });

  it("draws only the labels that fit in a dense graph, keeping the selected one", () => {
    const nodes = Array.from({ length: 60 }, (_, index) => ({
      id: `d${index}`,
      name: `Multi-agent Collaboration ${index}`,
      label: "Concept",
      matched: true,
      score: null,
      collectionId: "kg",
      properties: {},
    }));
    const edges = nodes.slice(1).map((node, index) => ({
      id: `e${index}`,
      source: "d0",
      target: node.id,
      type: "RELATED_TO",
      collectionId: "kg",
      properties: {},
    }));

    render(
      <KnowledgeGraphSvg
        graph={{ nodes, edges }}
        width={600}
        height={400}
        labels="all"
        selectedNodeId="d37"
        ariaLabel="graph"
      />
    );

    const labelled = nodes.filter((node) => screen.queryByText(node.name));
    expect(screen.getAllByTestId("knowledge-search-node")).toHaveLength(60);
    expect(labelled.length).toBeGreaterThan(0);
    expect(labelled.length).toBeLessThan(nodes.length);
    expect(
      screen.getByText("Multi-agent Collaboration 37")
    ).toBeInTheDocument();
  });

  it("selects nodes by click and keyboard when interactive", async () => {
    const user = userEvent.setup();
    const onSelectNode = jest.fn();
    render(
      <KnowledgeGraphSvg
        graph={searchGraph}
        width={600}
        height={400}
        labels="all"
        selectedNodeId="n2"
        onSelectNode={onSelectNode}
        ariaLabel="graph"
      />
    );

    const matched = screen.getByRole("button", {
      name: "Veri Saklama Politikası, Policy",
    });
    await user.click(matched);
    expect(onSelectNode).toHaveBeenCalledWith(searchGraph.nodes[0]);

    const selected = screen.getByRole("button", {
      name: "Veri Koruma Sorumlusu, Role",
    });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    selected.focus();
    await user.keyboard("{Enter}");
    expect(onSelectNode).toHaveBeenLastCalledWith(searchGraph.nodes[1]);
  });

  it("is not focusable without a selection handler", () => {
    render(
      <KnowledgeGraphSvg
        graph={searchGraph}
        width={600}
        height={400}
        labels="none"
        ariaLabel="graph"
      />
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "graph" })).toBeInTheDocument();
  });
});
