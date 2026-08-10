import { screen, waitFor } from "@testing-library/react";

import { toast } from "@/hooks/useToast";
import {
  ResourceAssignmentPanel,
  type DirectResourcePermission,
} from "@/components/organization/ResourceAssignmentPanel";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/hooks/useToast", () => ({
  toast: {
    error: jest.fn(),
    success: jest.fn(),
  },
}));

const resources = [
  { id: "1", name: "Research agent" },
  { id: "2", name: "Support agent" },
];

const permissions: DirectResourcePermission[] = [
  {
    resource_id: "1",
    resource_name: "Research agent",
    permission_level: "read",
  },
];

describe("ResourceAssignmentPanel", () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = jest.fn();
    HTMLElement.prototype.setPointerCapture = jest.fn();
    HTMLElement.prototype.releasePointerCapture = jest.fn();
    HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  it("filters resources and can show only selected assignments", async () => {
    const user = setupUser();

    render(
      <ResourceAssignmentPanel
        title="Agents"
        resources={resources}
        permissions={permissions}
        editable
        onSave={jest.fn()}
      />
    );

    await user.type(screen.getByPlaceholderText("Search agents"), "support");
    expect(screen.getByText("Support agent")).toBeInTheDocument();
    expect(screen.queryByText("Research agent")).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Search agents"));
    await user.click(screen.getByRole("checkbox", { name: "Selected only" }));
    expect(screen.getByText("Research agent")).toBeInTheDocument();
    expect(screen.queryByText("Support agent")).not.toBeInTheDocument();
  });

  it("saves the complete local selection as one direct-permission payload", async () => {
    const user = setupUser();
    const onSave = jest.fn().mockResolvedValue(undefined);

    render(
      <ResourceAssignmentPanel
        title="Agents"
        resources={resources}
        permissions={permissions}
        editable
        onSave={onSave}
      />
    );

    await user.click(
      screen.getByRole("checkbox", { name: "Select Support agent" })
    );
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith([
        {
          resource_id: "1",
          resource_name: "Research agent",
          permission_level: "read",
        },
        {
          resource_id: "2",
          resource_name: "Support agent",
          permission_level: "read",
        },
      ]);
    });
  });

  it("bulk-selects visible resources", async () => {
    const user = setupUser();
    render(
      <ResourceAssignmentPanel
        title="Agents"
        resources={resources}
        permissions={[]}
        editable
        onSave={jest.fn()}
      />
    );

    await user.type(screen.getByPlaceholderText("Search agents"), "support");
    await user.click(screen.getByRole("button", { name: "Select visible" }));

    expect(screen.getByRole("checkbox", { name: "Select Support agent" })).toHaveAttribute(
      "aria-checked",
      "true"
    );
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("treats access as a binary assignment without permission-level controls", () => {
    render(
      <ResourceAssignmentPanel
        title="Agents"
        resources={resources}
        permissions={permissions}
        editable
        onSave={jest.fn()}
      />
    );

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Assigned")).toBeInTheDocument();
  });

  it("retains dirty edits and surfaces backend detail after a save error", async () => {
    const user = setupUser();
    const onSave = jest.fn().mockRejectedValue(new Error("Unit scope denied"));

    render(
      <ResourceAssignmentPanel
        title="Agents"
        resources={resources}
        permissions={permissions}
        editable
        onSave={onSave}
      />
    );

    const supportCheckbox = screen.getByRole("checkbox", {
      name: "Select Support agent",
    });
    await user.click(supportCheckbox);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Unit scope denied");
    });
    expect(supportCheckbox).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("renders loading, empty, error, and read-only states", async () => {
    const { rerender } = render(
      <ResourceAssignmentPanel
        title="Collections"
        resources={[]}
        permissions={[]}
        editable={false}
        isLoading
        onSave={jest.fn()}
      />
    );

    expect(screen.getByText("Loading collections…")).toBeInTheDocument();

    rerender(
      <ResourceAssignmentPanel
        title="Collections"
        resources={[]}
        permissions={[]}
        editable={false}
        error="Collections could not be loaded"
        onRetry={jest.fn()}
        onSave={jest.fn()}
      />
    );
    expect(screen.getByText("Collections could not be loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();

    rerender(
      <ResourceAssignmentPanel
        title="Collections"
        resources={[]}
        permissions={[]}
        editable={false}
        onSave={jest.fn()}
      />
    );
    expect(screen.getByText("No collections available")).toBeInTheDocument();
    expect(screen.getByText("View only")).toBeInTheDocument();
  });
});
