import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@/i18n/config";

import { OrganizationDesigner } from "@/components/organization/OrganizationDesigner";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/components/organization/OrganizationDesignerInspector", () => ({
  OrganizationDesignerInspector: () => <aside>Inspector</aside>,
}));

describe("OrganizationDesigner real React Flow", () => {
  it("protects automatic positions from keyboard movement through real React Flow", async () => {
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
        canMoveOrganization
        capabilityLoading={false}
        globalAccess={false}
        onClose={jest.fn()}
        onSelectOrg={jest.fn()}
        onCreateOrg={jest.fn().mockResolvedValue(undefined)}
        onUpdateOrg={jest.fn().mockResolvedValue(undefined)}
        onDeleteOrg={jest.fn().mockResolvedValue(undefined)}
        onMoveOrg={jest.fn().mockResolvedValue(true)}
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

    await waitFor(() => expect(node.style.transform).toBe(initialTransform));
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
        canMoveOrganization
        capabilityLoading={false}
        globalAccess={false}
        onClose={jest.fn()}
        onSelectOrg={jest.fn()}
        onCreateOrg={onCreateOrg}
        onUpdateOrg={jest.fn().mockResolvedValue(undefined)}
        onDeleteOrg={jest.fn().mockResolvedValue(undefined)}
        onMoveOrg={jest.fn().mockResolvedValue(true)}
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
