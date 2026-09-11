import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { createFlowStore } from "../stores/flowStore";
import { useLoadFlowIntoStore } from "../hooks/useLoadFlowIntoStore";

jest.mock("@/lib/fetcher", () => ({
  errorHandlingFetcher: jest.fn(),
}));

const { errorHandlingFetcher } = jest.requireMock("@/lib/fetcher");

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

describe("useLoadFlowIntoStore", () => {
  afterEach(() => jest.clearAllMocks());

  it("fetches from the published endpoint when source is 'published' and loads the graph", async () => {
    errorHandlingFetcher.mockResolvedValue({
      nodes: [
        { id: "n1", type: "ChatInput", position: { x: 0, y: 0 }, values: {} },
      ],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
    });

    const store = createFlowStore();
    const { result } = renderHook(
      () => useLoadFlowIntoStore("def-1", store, { source: "published" }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(errorHandlingFetcher).toHaveBeenCalledWith(
      "/api/agent-definitions/def-1/flow/published"
    );
    expect(store.getState().nodes.map((n) => n.id)).toEqual(["n1"]);
    expect(result.current.nodes.map((n) => n.id)).toEqual(["n1"]);
    expect(result.current.nodesCount).toBe(1);
  });

  it("fetches a pinned version's endpoint and loads its nested flow_spec when source is { versionNo }", async () => {
    errorHandlingFetcher.mockResolvedValue({
      id: "v-3",
      version_no: 3,
      status: "archived",
      flow_spec: {
        nodes: [
          {
            id: "old1",
            type: "ChatInput",
            position: { x: 0, y: 0 },
            values: {},
          },
        ],
        edges: [],
        viewport: { x: 0, y: 0, zoom: 1 },
      },
    });

    const store = createFlowStore();
    const { result } = renderHook(
      () => useLoadFlowIntoStore("def-1", store, { source: { versionNo: 3 } }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(errorHandlingFetcher).toHaveBeenCalledWith(
      "/api/agent-definitions/def-1/flow/versions/3"
    );
    expect(store.getState().nodes.map((n) => n.id)).toEqual(["old1"]);
    expect(result.current.nodes.map((n) => n.id)).toEqual(["old1"]);
    expect(result.current.nodesCount).toBe(1);
  });

  it("defaults to the draft endpoint when no source is given", async () => {
    errorHandlingFetcher.mockResolvedValue({
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
    });
    const store = createFlowStore();

    renderHook(() => useLoadFlowIntoStore("def-1", store), { wrapper });

    await waitFor(() =>
      expect(errorHandlingFetcher).toHaveBeenCalledWith(
        "/api/agent-definitions/def-1/flow/draft"
      )
    );
  });
  it("falls back to the published spec when a pinned version fails to load", async () => {
    errorHandlingFetcher.mockImplementation((url: string) => {
      if (url.includes("/versions/")) {
        return Promise.reject(new Error("version endpoint unavailable"));
      }
      return Promise.resolve({
        nodes: [
          {
            id: "pub1",
            type: "ChatInput",
            position: { x: 0, y: 0 },
            values: {},
          },
        ],
        edges: [],
        viewport: { x: 0, y: 0, zoom: 1 },
      });
    });

    const store = createFlowStore();
    const { result } = renderHook(
      () => useLoadFlowIntoStore("def-1", store, { source: { versionNo: 9 } }),
      { wrapper }
    );

    await waitFor(() =>
      expect(result.current.nodes.map((n) => n.id)).toEqual(["pub1"])
    );
    expect(errorHandlingFetcher).toHaveBeenCalledWith(
      "/api/agent-definitions/def-1/flow/published"
    );
  });
});
