/**
 * Regression test for: opening a flow's viewer modal showed "no flow
 * designed" even for flows with published versions.
 *
 * Root cause: the preview read the *draft* endpoint. Publishing consumes
 * the draft row (FlowVersionRepository.publish_draft promotes it), so a
 * flow whose draft has been published — or discarded on exit — has no
 * draft to read and the preview 404'd into its empty state. The modal
 * must show what is published, i.e. what chat actually runs.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { FlowAgentPreview } from "../FlowAgentPreview";

const mockPush = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
  }),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: unknown) =>
      typeof fallback === "string" ? fallback : _key,
  }),
}));

jest.mock("@/lib/fetcher", () => ({ errorHandlingFetcher: jest.fn() }));

jest.mock("../../FlowCanvas", () => ({
  FlowCanvas: () => <div data-testid="flow-canvas" />,
}));

jest.mock("../../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => ({ data: {} }),
}));

jest.mock("../../hooks/useCanvasWiring", () => ({
  useHandleTypeLookup: () => () => ({}),
}));

jest.mock("../../nodes/registry", () => ({ createNodeTypes: () => ({}) }));

const { errorHandlingFetcher } = jest.requireMock("@/lib/fetcher");

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

const PUBLISHED_SPEC = {
  version: "1.0",
  nodes: [
    { id: "n1", type: "ChatInput", position: { x: 0, y: 0 }, values: {} },
    { id: "n2", type: "ChatOutput", position: { x: 200, y: 0 }, values: {} },
  ],
  edges: [{ id: "e1", source: "n1", target: "n2" }],
  viewport: { x: 0, y: 0, zoom: 1 },
};

describe("FlowAgentPreview", () => {
  afterEach(() => jest.clearAllMocks());

  it("previews the published flow, not the mutable draft", async () => {
    errorHandlingFetcher.mockResolvedValue(PUBLISHED_SPEC);

    render(<FlowAgentPreview definitionId="def-1" />, { wrapper });

    await waitFor(() => expect(errorHandlingFetcher).toHaveBeenCalled());

    const urls = errorHandlingFetcher.mock.calls.map((c: unknown[]) =>
      String(c[0])
    );
    expect(urls).toContain("/api/agent-definitions/def-1/flow/published");
    expect(urls).not.toContain("/api/agent-definitions/def-1/flow/draft");

    expect(await screen.findByTestId("flow-canvas")).toBeInTheDocument();
  });

  it("keeps its empty state when nothing has ever been published", async () => {
    errorHandlingFetcher.mockRejectedValue(
      Object.assign(new Error("Not Found"), { status: 404 })
    );

    render(<FlowAgentPreview definitionId="def-1" />, { wrapper });

    expect(
      await screen.findByText("No flow designed for this agent yet.")
    ).toBeInTheDocument();
  });

  it("renders open flow editor button when canEdit is true and invokes onEdit when clicked", async () => {
    errorHandlingFetcher.mockResolvedValue(PUBLISHED_SPEC);
    const mockOnEdit = jest.fn();

    render(
      <FlowAgentPreview
        definitionId="def-1"
        canEdit={true}
        onEdit={mockOnEdit}
      />,
      { wrapper }
    );

    const button = await screen.findByTestId("open-flow-editor-button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("Akış Düzenleyicisini Aç");

    fireEvent.click(button);
    expect(mockOnEdit).toHaveBeenCalledTimes(1);
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("navigates to /app/flows/{definitionId} when canEdit is true and onEdit is omitted", async () => {
    errorHandlingFetcher.mockResolvedValue(PUBLISHED_SPEC);

    render(<FlowAgentPreview definitionId="def-42" canEdit={true} />, {
      wrapper,
    });

    const button = await screen.findByTestId("open-flow-editor-button");
    fireEvent.click(button);

    expect(mockPush).toHaveBeenCalledWith("/app/flows/def-42");
  });

  it("does not render open flow editor button when canEdit is false", async () => {
    errorHandlingFetcher.mockResolvedValue(PUBLISHED_SPEC);

    render(<FlowAgentPreview definitionId="def-1" canEdit={false} />, {
      wrapper,
    });

    await screen.findByTestId("flow-canvas");
    expect(screen.queryByTestId("open-flow-editor-button")).toBeNull();
  });
});
