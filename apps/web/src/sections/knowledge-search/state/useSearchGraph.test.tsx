import { act, renderHook } from "@testing-library/react";

import { useSearchGraph } from "@/sections/knowledge-search/state/useSearchGraph";
import { useKnowledgeNeighborhoods } from "@/lib/api/domains/knowledge/hooks";
import { fetchKnowledgeNeighborhood } from "@/lib/api/domains/knowledge/api";
import {
  searchGraph,
  searchResponse,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";
import type {
  KnowledgeGraph,
  KnowledgeSearchResponse,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

jest.mock("@/lib/api/domains/knowledge/hooks", () => ({
  useKnowledgeNeighborhoods: jest.fn(),
}));
jest.mock("@/lib/api/domains/knowledge/api", () => ({
  fetchKnowledgeNeighborhood: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({ toast: { error: jest.fn() } }));
jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

const neighborhoods = jest.mocked(useKnowledgeNeighborhoods);
const fetchNeighborhood = jest.mocked(fetchKnowledgeNeighborhood);

const neighbor: KnowledgeGraph = {
  nodes: [
    {
      id: "n9",
      name: "İmha Tutanağı",
      label: "Document",
      matched: false,
      score: null,
      collectionId: "kg",
      properties: {},
    },
  ],
  edges: [
    {
      id: "e9",
      source: "n2",
      target: "n9",
      type: "ONAYLAR",
      collectionId: "kg",
      properties: {},
    },
  ],
};

interface Props {
  result: KnowledgeSearchResponse | undefined;
  entityLabels?: readonly string[];
}

function setup(initial: Props) {
  return renderHook(
    ({ result, entityLabels = [] }: Props) =>
      useSearchGraph({
        result,
        depth: 1,
        matchedOnly: false,
        entityLabels,
        canExpand: true,
      }),
    { initialProps: initial }
  );
}

const ids = (graph: KnowledgeGraph) => graph.nodes.map((node) => node.id);

beforeEach(() => {
  neighborhoods.mockReturnValue({
    graphs: [],
    error: undefined,
    isLoading: false,
  });
  fetchNeighborhood.mockReset();
});

describe("useSearchGraph", () => {
  it("shows the result graph, refined to the chosen entity labels", () => {
    const result = searchResponse();
    const { result: hook, rerender } = setup({ result });
    expect(ids(hook.current.graph)).toEqual(["n1", "n2"]);

    rerender({ result, entityLabels: ["policy"] });

    expect(ids(hook.current.graph)).toEqual(["n1"]);
    // Everything known stays available, e.g. to preview a filtered-out node.
    expect(ids(hook.current.fullGraph)).toEqual(["n1", "n2"]);
  });

  it("is empty while there is no result", () => {
    const { result: hook } = setup({ result: undefined });

    expect(hook.current.graph).toEqual({ nodes: [], edges: [] });
  });

  it("merges manual expansions into the graph", async () => {
    fetchNeighborhood.mockResolvedValue(neighbor);
    const result = searchResponse();
    const { result: hook } = setup({ result });

    await act(async () => {
      await hook.current.expandNode(searchGraph.nodes[1]!);
    });

    expect(ids(hook.current.graph)).toEqual(["n1", "n2", "n9"]);
  });

  it("drops manual expansions when a new result arrives", async () => {
    fetchNeighborhood.mockResolvedValue(neighbor);
    const first = searchResponse();
    const { result: hook, rerender } = setup({ result: first });
    await act(async () => {
      await hook.current.expandNode(searchGraph.nodes[1]!);
    });
    expect(ids(hook.current.graph)).toContain("n9");

    rerender({ result: searchResponse({ query: "başka sorgu" }) });

    expect(ids(hook.current.graph)).toEqual(["n1", "n2"]);
  });

  it("does not carry a previous result's expansion into the next expansion", async () => {
    const second = {
      ...neighbor,
      nodes: [{ ...neighbor.nodes[0]!, id: "n10" }],
    };
    fetchNeighborhood
      .mockResolvedValueOnce(neighbor)
      .mockResolvedValueOnce({ nodes: second.nodes, edges: [] });
    const { result: hook, rerender } = setup({ result: searchResponse() });
    await act(async () => {
      await hook.current.expandNode(searchGraph.nodes[1]!);
    });

    rerender({ result: searchResponse({ query: "başka sorgu" }) });
    await act(async () => {
      await hook.current.expandNode(searchGraph.nodes[1]!);
    });

    expect(ids(hook.current.graph)).toEqual(["n1", "n2", "n10"]);
  });
});
