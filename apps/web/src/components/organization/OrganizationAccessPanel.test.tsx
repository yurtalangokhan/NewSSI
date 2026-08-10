import { screen, waitFor } from "@testing-library/react";

import { usePersonaOptions } from "@/hooks/usePersonaOptions";
import { useCollections } from "@/lib/langconnect";
import { OrganizationAccessPanel } from "@/components/organization/OrganizationAccessPanel";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/hooks/usePersonaOptions", () => ({ usePersonaOptions: jest.fn() }));
jest.mock("@/lib/langconnect", () => ({ useCollections: jest.fn() }));

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
    mockedUsePersonaOptions.mockReturnValue({
      personas: [{ id: 11, name: "Research agent", description: "" }],
      error: undefined,
      isLoading: false,
      refresh: jest.fn(),
    });
    mockedUseCollections.mockReturnValue({
      collections: [{ uuid: "collection-1", name: "Policies" }],
      error: undefined,
      isLoading: false,
      mutate: jest.fn(),
    });
    jest.spyOn(global, "fetch").mockImplementation(async (_request) => {
      // Serves scoped direct-permission GET requests.
      return new Response(JSON.stringify({ permissions: [], count: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders separate agent and collection panels for the organization target", async () => {
    render(
      <OrganizationAccessPanel
        organization={{ id: "org-1", name: "Platform" }}
        members={[]}
        editable
      />
    );

    expect(screen.getByRole("tab", { name: "Unit access" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Member access" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Research agent")).toBeInTheDocument();
      expect(screen.getByText("Policies")).toBeInTheDocument();
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/permissions/organizations/org-1/targets/organization/org-1/resources/agent"
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/user-service/permissions/organizations/org-1/targets/organization/org-1/resources/rag_collection"
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
      />
    );

    await user.click(screen.getByRole("tab", { name: "Member access" }));
    await user.click(screen.getByRole("combobox", { name: "Member" }));
    expect((await screen.findAllByText("active@example.com")).length).toBeGreaterThan(0);
    expect(screen.queryByText("inactive@example.com")).not.toBeInTheDocument();
  });

  it("loads and saves the exact selected member agent target", async () => {
    const user = setupUser();
    const fetchMock = jest.mocked(global.fetch);
    fetchMock.mockImplementation(async (_request, options) => {
      if (options?.method === "PUT") {
        return new Response(
          JSON.stringify({
            permissions: [
              {
                resource_id: "11",
                resource_name: "Research agent",
                permission_level: "read",
              },
            ],
            count: 1,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ permissions: [], count: 0 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
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
      />
    );

    await user.click(screen.getByRole("tab", { name: "Member access" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/user-service/permissions/organizations/org-1/targets/user/user-1/resources/agent"
      )
    );
    await user.click(screen.getByRole("checkbox", { name: "Select Research agent" }));
    await user.click(screen.getAllByRole("button", { name: "Save changes" })[0]!);

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
  });
});
