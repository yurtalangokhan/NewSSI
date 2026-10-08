import { envelopeResponse, fakeResponse } from "@tests/setup/responseModel";
import { useCallback, useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import "@/i18n/config";

import { usePersonaOptions } from "@/lib/api/domains/agents/hooks";
import { useCollections } from "@/lib/api/domains/knowledge/hooks";
import {
  OrganizationAccessPanel,
  type ResourceType,
} from "@/components/organization/OrganizationAccessPanel";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/lib/api/domains/agents/hooks", () => ({
  usePersonaOptions: jest.fn(),
}));
jest.mock("@/lib/api/domains/knowledge/hooks", () => ({
  useCollections: jest.fn(),
}));

const mockedUsePersonaOptions = jest.mocked(usePersonaOptions);
const mockedUseCollections = jest.mocked(useCollections);

describe("OrganizationAccessPanel", () => {
  beforeAll(() => {
    HTMLElement.prototype.hasPointerCapture = jest.fn();
    HTMLElement.prototype.setPointerCapture = jest.fn();
    HTMLElement.prototype.releasePointerCapture = jest.fn();
    HTMLElement.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    jest.spyOn(global, "fetch").mockImplementation(async (request) => {
      const resources = String(request).includes("rag_collection")
        ? [{ id: "collection-1", name: "Policies" }]
        : [{ id: "11", name: "Research agent", description: "" }];
      return envelopeResponse(
        { resources, permissions: [], count: 0 },
        { status: 200 }
      );
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it.each<ResourceType>(["agent", "rag_collection"])(
    "keeps parent loading state stable for %s until loading completes",
    async (resourceType) => {
      const notifications = jest.fn();
      let resolveWorkspace!: (response: Response) => void;
      jest
        .mocked(global.fetch)
        .mockImplementationOnce(
          () => new Promise<Response>((resolve) => (resolveWorkspace = resolve))
        );

      function LoadingParent({ visible = true }: { visible?: boolean }) {
        const [loading, setLoading] = useState({
          agent: false,
          rag_collection: false,
        });
        const handleLoading = useCallback(
          (type: ResourceType, value: boolean) => {
            notifications(type, value);
            // Bound the regression so a render loop fails promptly.
            if (notifications.mock.calls.length > 20) {
              throw new Error("Loading notifications did not settle");
            }
            setLoading((current) =>
              current[type] === value ? current : { ...current, [type]: value }
            );
          },
          []
        );
        return (
          <>
            <output aria-label="Access loading">
              {String(loading[resourceType])}
            </output>
            {visible && (
              <OrganizationAccessPanel
                organization={{ id: "org-1", name: "Platform" }}
                members={[]}
                editable
                resourceType={resourceType}
                onLoadingChange={handleLoading}
              />
            )}
          </>
        );
      }

      const { rerender } = render(<LoadingParent />);
      expect(screen.getByLabelText("Access loading")).toHaveTextContent("true");
      resolveWorkspace(
        envelopeResponse(
          { resources: [], permissions: [], count: 0 },
          { status: 200 }
        )
      );
      await waitFor(() =>
        expect(screen.getByLabelText("Access loading")).toHaveTextContent(
          "false"
        )
      );
      rerender(<LoadingParent visible={false} />);
      expect(screen.getByLabelText("Access loading")).toHaveTextContent(
        "false"
      );
    }
  );

  it("renders only the requested agent panel for the organization target", async () => {
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[]}
        editable
        resourceType="agent"
      />
    );

    expect(
      screen.getByRole("tab", { name: "Unit access" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Member access" })
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Research agent")).toBeInTheDocument();
    });
    expect(screen.queryByText("Policies")).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/permissions/organizations/org-1/targets/organization/org-1/resources/agent/workspace",
      expect.any(Object)
    );
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/resources/rag_collection"),
      expect.any(Object)
    );
  });

  it("renders only the requested collection panel", async () => {
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[]}
        editable
        resourceType="rag_collection"
      />
    );

    await waitFor(() =>
      expect(screen.getByText("Policies")).toBeInTheDocument()
    );
    expect(screen.queryByText("Research agent")).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/permissions/organizations/org-1/targets/organization/org-1/resources/rag_collection/workspace",
      expect.any(Object)
    );
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/resources/agent"),
      expect.any(Object)
    );
  });

  it("offers only active organization members as user targets", async () => {
    const user = setupUser();
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[
          {
            id: "membership-1",
            user_id: "active-user",
            role_in_org: "member",
            is_active: true,
            user: { id: "active-user", email: "active@example.com" },
          },
          {
            id: "membership-2",
            user_id: "inactive-user",
            role_in_org: "viewer",
            is_active: false,
            user: { id: "inactive-user", email: "inactive@example.com" },
          },
        ]}
        editable
        resourceType="agent"
      />
    );

    await user.click(screen.getByRole("tab", { name: "Member access" }));
    await user.click(screen.getByRole("combobox", { name: "Member" }));
    expect(
      (await screen.findAllByText("active@example.com")).length
    ).toBeGreaterThan(0);
    expect(screen.queryByText("inactive@example.com")).not.toBeInTheDocument();
  });

  it("loads and saves the exact selected member agent target", async () => {
    const user = setupUser();
    const onSaveComplete = jest.fn();
    const fetchMock = jest.mocked(global.fetch);
    // Serves scoped permission GET and PUT requests for the selected member.
    fetchMock.mockImplementation(async (_request, options) => {
      if (options?.method === "PUT") {
        return envelopeResponse(
          {
            permissions: [
              {
                resource_id: "11",
                resource_name: "Research agent",
                permission_level: "read",
              },
            ],
            count: 1,
          },
          { status: 200 }
        );
      }
      return envelopeResponse(
        {
          resources: [{ id: "11", name: "Research agent", description: "" }],
          permissions: [],
          count: 0,
        },
        { status: 200 }
      );
    });
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[
          {
            id: "membership-1",
            user_id: "user-1",
            role_in_org: "member",
            is_active: true,
            user: { id: "user-1", email: "member@example.com" },
          },
        ]}
        editable
        resourceType="agent"
        onSaveComplete={onSaveComplete}
      />
    );

    await user.click(screen.getByRole("tab", { name: "Member access" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/user-service/permissions/organizations/org-1/targets/user/user-1/resources/agent/workspace",
        expect.any(Object)
      )
    );
    await user.click(
      await screen.findByRole("checkbox", { name: "Select Research agent" })
    );
    await user.click(
      screen.getAllByRole("button", { name: "Save changes" })[0]!
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/user-service/permissions/organizations/org-1/targets/user/user-1/resources/agent",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            permissions: [
              {
                resource_id: "11",
                resource_name: "Research agent",
                permission_level: "read",
              },
            ],
          }),
        })
      )
    );
    expect(onSaveComplete).toHaveBeenCalledTimes(1);
  });

  it("keeps a successful permission save successful when count refresh fails", async () => {
    const user = setupUser();
    const onSaveComplete = jest
      .fn()
      .mockRejectedValue(new Error("Tree unavailable"));
    // Serves scoped permission GET and PUT requests for the ancillary-refresh case.
    jest.mocked(global.fetch).mockImplementation(async (_request, options) => {
      if (options?.method === "PUT") {
        return envelopeResponse(
          {
            permissions: [
              {
                resource_id: "11",
                resource_name: "Research agent",
                permission_level: "read",
              },
            ],
            count: 1,
          },
          { status: 200 }
        );
      }
      return envelopeResponse(
        {
          resources: [{ id: "11", name: "Research agent", description: "" }],
          permissions: [],
          count: 0,
        },
        { status: 200 }
      );
    });
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[]}
        editable
        resourceType="agent"
        onSaveComplete={onSaveComplete}
      />
    );

    await user.click(
      await screen.findByRole("checkbox", { name: "Select Research agent" })
    );
    const save = screen.getAllByRole("button", { name: "Save changes" })[0]!;
    await user.click(save);

    await waitFor(() => expect(onSaveComplete).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(save).toBeDisabled());
    expect(screen.getByText("Research agent")).toBeInTheDocument();
  });

  it("disables editing after a workspace error and retries the same request", async () => {
    const user = setupUser();
    const fetchMock = jest.mocked(global.fetch);
    fetchMock
      .mockResolvedValueOnce(
        fakeResponse(false, 502, { detail: "Catalog unavailable" })
      )
      .mockResolvedValueOnce(
        envelopeResponse(
          {
            resources: [{ id: "11", name: "Research agent" }],
            permissions: [],
            count: 0,
          },
          { status: 200 }
        )
      );

    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[]}
        editable
        resourceType="agent"
      />
    );

    expect(await screen.findByText("Catalog unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Research agent")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/user-service/permissions/organizations/org-1/targets/organization/org-1/resources/agent/workspace",
      expect.any(Object)
    );
  });
});
