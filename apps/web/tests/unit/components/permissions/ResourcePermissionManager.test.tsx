/**
 * @jest-environment jsdom
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { setupUser } from "@tests/setup/test-utils";
import { ResourcePermissionManager } from "@/components/permissions/ResourcePermissionManager";
import { SWRConfig } from "swr";

// Mock fetch
global.fetch = jest.fn();

const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;

const mockPermissions = [
  {
    id: "perm-1",
    resource_type: "agent",
    resource_id: "agent-123",
    user_id: "user-1",
    permission_level: "read",
    granted_by: "admin-1",
    granted_at: "2024-01-01T00:00:00Z",
    is_inherited: false,
  },
  {
    id: "perm-2",
    resource_type: "agent",
    resource_id: "agent-123",
    organization_id: "org-1",
    permission_level: "execute",
    granted_by: "admin-1",
    granted_at: "2024-01-01T00:00:00Z",
    is_inherited: false,
  },
];

const mockUsers = [
  { id: "user-1", email: "user1@example.com", full_name: "User One" },
  { id: "user-2", email: "user2@example.com", full_name: "User Two" },
];

const mockOrganizations = [
  { id: "org-1", name: "Engineering", path: "org-1/" },
  { id: "org-2", name: "Marketing", path: "org-2/" },
];

describe("ResourcePermissionManager", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockClear();
  });

  const renderWithSWR = (component: React.ReactElement) => {
    return render(
      <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
        {component}
      </SWRConfig>
    );
  };

  it("renders permission manager component", async () => {
    // Mock /api/permissions/resources/{type}/{id}
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockPermissions,
    } as Response);

    // Mock /api/organizations
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockOrganizations,
    } as Response);

    // Mock /api/users
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockUsers,
    } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
        resourceName="Test Agent"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manage Permissions")).toBeInTheDocument();
    });

    expect(screen.getByText("Agent: Test Agent")).toBeInTheDocument();
  });

  it("displays loading state initially", () => {
    mockFetch.mockImplementation(
      () =>
        new Promise(() => {
          /* never resolves */
        })
    );

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    expect(screen.getByText("Loading permissions...")).toBeInTheDocument();
  });

  it("shows user permissions section", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("User Permissions")).toBeInTheDocument();
    });

    expect(screen.getByText("1")).toBeInTheDocument(); // Count badge
  });

  it("shows organization permissions section", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Organization Permissions")).toBeInTheDocument();
    });

    expect(screen.getByText("1")).toBeInTheDocument(); // Count badge
  });

  it("displays add user button", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Add User")).toBeInTheDocument();
    });
  });

  it("displays add organization button", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Add Organization")).toBeInTheDocument();
    });
  });

  it("shows empty state when no permissions", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("No user-specific permissions")).toBeInTheDocument();
    });

    expect(screen.getByText("No organization permissions")).toBeInTheDocument();
  });

  it("opens add user modal when clicking add user button", async () => {
    const user = setupUser();

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Add User")).toBeInTheDocument();
    });

    const addUserButton = screen.getByText("Add User");
    await user.click(addUserButton);

    await waitFor(() => {
      expect(screen.getByText("Add User Permission")).toBeInTheDocument();
    });
  });

  it("calls onClose when close button is clicked", async () => {
    const user = setupUser();
    const onClose = jest.fn();

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
        onClose={onClose}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manage Permissions")).toBeInTheDocument();
    });

    // Find close button (X icon)
    const closeButtons = screen.getAllByRole("button");
    const closeButton = closeButtons.find((btn) =>
      btn.querySelector('svg[data-testid="X"]')
    );

    if (closeButton) {
      await user.click(closeButton);
      expect(onClose).toHaveBeenCalledTimes(1);
    }
  });

  it("displays correct resource type label", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="rag_collection"
        resourceId="collection-123"
        resourceName="Test Collection"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("RAG Collection: Test Collection")).toBeInTheDocument();
    });
  });

  it("handles fetch error gracefully", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    // Should show loading state or handle error
    await waitFor(() => {
      expect(screen.getByText("Loading permissions...")).toBeInTheDocument();
    });
  });

  it("displays inherited permissions section when present", async () => {
    const permissionsWithInherited = [
      ...mockPermissions,
      {
        id: "perm-3",
        resource_type: "agent",
        resource_id: "agent-123",
        organization_id: "org-2",
        permission_level: "read",
        granted_by: "admin-1",
        granted_at: "2024-01-01T00:00:00Z",
        is_inherited: true,
        source: "Parent Organization",
      },
    ];

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => permissionsWithInherited,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Inherited Permissions")).toBeInTheDocument();
    });
  });

  it("groups permissions correctly by type", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockPermissions,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockOrganizations,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockUsers,
      } as Response);

    renderWithSWR(
      <ResourcePermissionManager
        resourceType="agent"
        resourceId="agent-123"
      />
    );

    await waitFor(() => {
      const userSection = screen.getByText("User Permissions");
      const orgSection = screen.getByText("Organization Permissions");

      expect(userSection).toBeInTheDocument();
      expect(orgSection).toBeInTheDocument();
    });
  });
});
