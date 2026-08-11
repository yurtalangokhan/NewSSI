import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@/i18n/config";

import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import { useOrganizationLayout } from "@/components/organization/useOrganizationLayout";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/components/organization/useOrganizationLayout", () => ({
  useOrganizationLayout: jest.fn(),
}));

jest.mock("@/components/organization/OrganizationDesignerInspector", () => ({
  OrganizationDesignerInspector: () => <aside>Inspector</aside>,
}));

const mockedUseOrganizationLayout = jest.mocked(useOrganizationLayout);

describe("OrganizationDesigner with React Flow", () => {
  const setPosition = jest.fn();

  beforeEach(() => {
    mockedUseOrganizationLayout.mockReturnValue({
      positions: { root: { x: 20, y: 30 } },
      writableOrganizationIds: new Set(["root"]),
      status: "idle",
      error: undefined,
      isLoading: false,
      hasDirtyPositions: false,
      isWritable: () => true,
      setPosition,
      flush: jest.fn().mockResolvedValue(true),
      retry: jest.fn().mockResolvedValue(true),
      discard: jest.fn(),
      refresh: jest.fn(),
    });
  });

  it("renders keyboard position changes through the real controlled React Flow", async () => {
    const user = setupUser();
    const { container } = render(
      <OrganizationDesigner
        organizations={[
          {
            id: "root",
            name: "Enterprise",
            path: "/enterprise",
            parent_id: null,
            children: [],
          },
        ]}
        selectedOrg={null}
        members={[]}
        editable
        canCreateRoot={false}
        canEditLayout
        capabilityLoading={false}
        onClose={jest.fn()}
        onSelectOrg={jest.fn()}
        onCreateOrg={jest.fn().mockResolvedValue(undefined)}
        onUpdateOrg={jest.fn().mockResolvedValue(undefined)}
        onDeleteOrg={jest.fn().mockResolvedValue(undefined)}
        onMoveOrg={jest.fn().mockResolvedValue(undefined)}
        onAddUser={jest.fn().mockResolvedValue(undefined)}
        onRoleChange={jest.fn().mockResolvedValue(undefined)}
        onRemoveUser={jest.fn().mockResolvedValue(undefined)}
      />
    );

    const node = await waitFor(() => {
      const candidate = container.ownerDocument.querySelector<HTMLElement>(
        '.react-flow__node[data-id="root"]'
      );
      expect(candidate).not.toBeNull();
      return candidate!;
    });
    const initialTransform = node.style.transform;
    fireEvent.click(node);
    node.focus();
    await user.keyboard("{ArrowRight}");

    await waitFor(() =>
      expect(node.style.transform).not.toBe(initialTransform)
    );
    expect(setPosition).toHaveBeenCalledWith("root", { x: 25, y: 30 });
  });

  it("creates a child from a temporary connected canvas node", async () => {
    const user = setupUser();
    const onCreateOrg = jest.fn().mockResolvedValue(undefined);
    const organization = {
      id: "root",
      name: "Enterprise",
      path: "/enterprise",
      parent_id: null,
      children: [],
    };
    const promptSpy = jest.spyOn(window, "prompt");

    render(
      <OrganizationDesigner
        organizations={[organization]}
        selectedOrg={organization}
        members={[]}
        editable
        canCreateRoot={false}
        canEditLayout
        capabilityLoading={false}
        onClose={jest.fn()}
        onSelectOrg={jest.fn()}
        onCreateOrg={onCreateOrg}
        onUpdateOrg={jest.fn().mockResolvedValue(undefined)}
        onDeleteOrg={jest.fn().mockResolvedValue(undefined)}
        onMoveOrg={jest.fn().mockResolvedValue(undefined)}
        onAddUser={jest.fn().mockResolvedValue(undefined)}
        onRoleChange={jest.fn().mockResolvedValue(undefined)}
        onRemoveUser={jest.fn().mockResolvedValue(undefined)}
      />
    );

    await user.click(
      await waitFor(() =>
        screen.getByLabelText("Add child to Enterprise", {
          selector: "button",
        })
      )
    );
    const draftName = await screen.findByLabelText(
      "New child organization name",
      { selector: "input" }
    );
    await user.type(draftName, "Security");
    await user.keyboard("{Enter}");

    expect(promptSpy).not.toHaveBeenCalled();
    expect(onCreateOrg).toHaveBeenCalledWith("root", "Security");
  });
});
