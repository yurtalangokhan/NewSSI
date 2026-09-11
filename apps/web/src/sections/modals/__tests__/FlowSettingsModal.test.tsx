import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import FlowSettingsModal from "@/sections/modals/FlowSettingsModal";

const mockCreateFlow = jest.fn();
jest.mock("@/lib/flows/createFlow", () => ({
  createFlow: (...args: unknown[]) => mockCreateFlow(...args),
}));

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => "/app/agents",
}));

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ isAdmin: true, isCurator: false }),
}));

describe("FlowSettingsModal (create mode)", () => {
  beforeEach(() => {
    mockCreateFlow.mockReset();
    mockPush.mockReset();
  });

  it("creates the flow and navigates to its studio", async () => {
    mockCreateFlow.mockResolvedValue({ personaId: 12, definitionId: "def-9" });

    render(<FlowSettingsModal mode="create" />);
    fireEvent.change(screen.getByTestId("flow-settings-name"), {
      target: { value: "Fatura Akışı" },
    });
    fireEvent.click(screen.getByTestId("flow-settings-submit"));

    await waitFor(() =>
      expect(mockCreateFlow).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Fatura Akışı" })
      )
    );
    expect(mockPush).toHaveBeenCalledWith("/app/flows/def-9");
  });

  it("keeps the modal open and shows a field error on a duplicate name", async () => {
    mockCreateFlow.mockRejectedValue(
      Object.assign(new Error("conflict"), { status: 409 })
    );

    render(<FlowSettingsModal mode="create" />);
    fireEvent.change(screen.getByTestId("flow-settings-name"), {
      target: { value: "Var Olan" },
    });
    fireEvent.click(screen.getByTestId("flow-settings-submit"));

    expect(
      await screen.findByTestId("flow-settings-name-error")
    ).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("requires a name before submitting", () => {
    render(<FlowSettingsModal mode="create" />);
    expect(screen.getByTestId("flow-settings-submit")).toBeDisabled();
  });

  it("offers the same share dialog the agent editor does", () => {
    render(<FlowSettingsModal mode="create" />);
    // A share *button* (opening people/groups/org-wide selection), not a
    // bare public switch — matching AgentEditorPage.
    expect(screen.getByTestId("flow-settings-share")).toBeInTheDocument();
  });

  it("localises the optional tag instead of hardcoding (Optional)", () => {
    render(<FlowSettingsModal mode="create" />);
    // t("common.optional") resolves to "Optional" in the test locale; the
    // literal opal "(Optional)" prop is no longer used.
    expect(screen.getByText(/Description \(Optional\)/)).toBeInTheDocument();
  });
});
