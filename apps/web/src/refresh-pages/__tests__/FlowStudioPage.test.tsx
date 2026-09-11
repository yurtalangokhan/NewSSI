import { render, screen } from "@testing-library/react";
import FlowStudioPage from "@/refresh-pages/FlowStudioPage";

jest.mock("@/refresh-pages/FlowAgentEditorPage", () => ({
  __esModule: true,
  default: ({ agentDefinitionId }: { agentDefinitionId: string }) => (
    <div data-testid="flow-canvas-mock">{agentDefinitionId}</div>
  ),
}));

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => "/app/flows/def-3",
}));

describe("FlowStudioPage", () => {
  it("mounts the canvas full-screen for the given definition", () => {
    render(<FlowStudioPage definitionId="def-3" />);

    expect(screen.getByTestId("flow-canvas-mock")).toHaveTextContent("def-3");
    expect(screen.getByTestId("flow-studio-root")).toHaveClass("h-screen");
  });
});
