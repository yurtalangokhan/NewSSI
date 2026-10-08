import { screen, waitFor, within } from "@testing-library/react";

import RolesPage from "@/app/admin/roles/page";
import {
  createCoarseRole,
  createCompositeRole,
  deleteCoarseRoleResponse,
  updateCoarseRolePermissions,
  updateCompositeRoleIds,
} from "@/lib/api/domains/access/api";
import { render, setupUser } from "@tests/setup/test-utils";

const chatId = "11111111-1111-4111-8111-111111111111";
const knowledgeId = "22222222-2222-4222-8222-222222222222";
const operatorId = "33333333-3333-4333-8333-333333333333";
const mockMutate = jest.fn().mockResolvedValue(undefined);
const mockRefresh = jest.fn().mockResolvedValue(undefined);
let mockDistributionLoading = false;
const mockCatalog: Record<string, unknown> = {
  "/api/user-service/roles/": {
    roles: [
      {
        id: operatorId,
        name: "custom-operator",
        description: "Operator",
        permissions: [],
        role_ids: [chatId],
        is_builtin: false,
        is_admin: false,
      },
    ],
  },
  "/api/user-service/coarse-roles/": {
    roles: [
      {
        id: chatId,
        name: "feature-chat",
        description: "Chat",
        service_client: "agent-service",
        permissions: ["chat:read"],
        is_builtin: true,
      },
      {
        id: knowledgeId,
        name: "feature-knowledge",
        description: "Knowledge",
        service_client: "rag-service",
        permissions: ["knowledge:read"],
        is_builtin: false,
      },
    ],
  },
  "/api/user-service/permissions/": { permissions: [] },
  "/api/user-service/coarse-roles/service-clients/list": {
    service_clients: ["agent-service-client", "rag-service-client"],
  },
  [`/api/user-service/roles/${operatorId}/role-ids`]: {
    name: "custom-operator",
    role_ids: [chatId],
  },
  [`/api/user-service/roles/${operatorId}/permissions`]: {
    name: "custom-operator",
    permissions: [],
    // The API returns the assigned bundles alongside effective permissions.
    role_ids: [chatId],
  },
};

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ hasPermission: () => true }),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock("@/i18n/config", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
}));
jest.mock("@/lib/auth/roles", () => ({
  formatRoleName: (name: string) => name,
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/lib/api/domains/access/api", () => ({
  createCompositeRole: jest.fn(),
  createCoarseRole: jest.fn(),
  deleteCoarseRoleResponse: jest.fn(),
  fetchRoleServiceClients: jest.fn(),
  deleteCompositeRoleResponse: jest.fn(),
  fetchCoarseRolePermissionsByName: jest.fn(),
  fetchCoarseRoles: jest.fn(),
  fetchCompositeRolePermissions: jest.fn(),
  fetchCompositeRoles: jest.fn(),
  fetchPermissionCatalog: jest.fn(),
  fetchRoleDistribution: jest.fn(),
  patchCompositeRole: jest.fn(),
  updateCoarseRolePermissions: jest.fn(),
  updateCompositeRoleIds: jest.fn(),
}));
jest.mock("swr", () => ({
  ...jest.requireActual("swr"),
  __esModule: true,
  default: (key: string | null) => ({
    data: key ? mockCatalog[key] : undefined,
    isLoading:
      key === "/api/user-service/users/role-distribution" &&
      mockDistributionLoading,
    mutate: mockMutate,
  }),
  useSWRConfig: () => ({ mutate: mockRefresh }),
}));
jest.mock("swr/mutation", () => ({
  __esModule: true,
  default: (key: string, fetcher: Function, options: any) => ({
    isMutating: false,
    trigger: async (arg: unknown) => {
      const result = await fetcher(key, { arg });
      options?.onSuccess?.(result);
      return result;
    },
  }),
}));

beforeEach(() => {
  mockDistributionLoading = false;
  jest.mocked(updateCompositeRoleIds).mockResolvedValue({
    ok: true,
    json: async () => ({
      effective_permissions: ["chat:read", "knowledge:read"],
    }),
  } as Response);
});

test("creates a realm composite from the composite tab", async () => {
  const user = setupUser();
  jest.mocked(createCompositeRole).mockResolvedValue({
    ok: true,
    json: async () => ({ id: "new-composite" }),
  } as Response);
  render(<RolesPage />);
  await user.click(screen.getByRole("button", { name: "newRoleButton" }));
  expect(screen.getAllByText("createCompositeRoleTitle")).toHaveLength(2);
  await user.type(
    screen.getByPlaceholderText("compositeRoleNamePlaceholder"),
    "new-composite"
  );
  await user.click(
    screen.getByRole("button", { name: "createCompositeRoleTitle" })
  );
  await waitFor(() =>
    expect(createCompositeRole).toHaveBeenCalledWith({
      name: "new-composite",
      description: "",
    })
  );
  expect(createCoarseRole).not.toHaveBeenCalled();
});

test("creates a client feature package only after selecting a service client", async () => {
  const user = setupUser();
  HTMLElement.prototype.hasPointerCapture = () => false;
  HTMLElement.prototype.setPointerCapture = () => {};
  HTMLElement.prototype.releasePointerCapture = () => {};
  HTMLElement.prototype.scrollIntoView = () => {};
  jest.mocked(createCoarseRole).mockResolvedValue({
    ok: true,
    json: async () => ({ id: "new-bundle" }),
  } as Response);
  render(<RolesPage />);
  await user.click(screen.getByRole("tab", { name: "featureBundlesTabLabel" }));
  await user.click(
    screen.getByRole("button", { name: "newFeatureBundleButton" })
  );
  expect(screen.getAllByText("createFeatureBundleTitle")).toHaveLength(2);
  await user.type(
    screen.getByPlaceholderText("featureBundleNamePlaceholder"),
    "my-feature"
  );
  const create = screen.getByRole("button", {
    name: "createFeatureBundleTitle",
  });
  expect(create).toBeDisabled();
  await user.click(
    screen.getByRole("combobox", { name: "serviceClientLabel" })
  );
  await user.click(
    screen.getByRole("option", { name: "agent-service-client" })
  );
  expect(create).toBeEnabled();
  await user.click(create);
  await waitFor(() =>
    expect(createCoarseRole).toHaveBeenCalledWith({
      name: "my-feature",
      service_client: "agent-service-client",
      description: "",
      permissions: [],
    })
  );
  expect(createCompositeRole).not.toHaveBeenCalled();
});

test("deletes a custom feature package but not a built-in one", async () => {
  const user = setupUser();
  jest
    .mocked(deleteCoarseRoleResponse)
    .mockResolvedValue({ ok: true } as Response);
  render(<RolesPage />);
  await user.click(screen.getByRole("tab", { name: "featureBundlesTabLabel" }));

  expect(
    screen.queryByRole("button", { name: "deleteButton" })
  ).not.toBeInTheDocument();
  await user.click(
    screen
      .getAllByText("feature-knowledge")
      .find((element) => element.closest('[role="button"]'))!
      .closest('[role="button"]')!
  );
  await user.click(screen.getByRole("button", { name: "deleteButton" }));
  expect(screen.getByText("deleteRoleTitle")).toBeInTheDocument();
  expect(deleteCoarseRoleResponse).not.toHaveBeenCalled();

  await user.click(
    screen.getAllByRole("button", { name: "deleteButton" }).at(-1)!
  );
  await waitFor(() =>
    expect(deleteCoarseRoleResponse).toHaveBeenCalledWith(knowledgeId)
  );
  expect(mockMutate).toHaveBeenCalled();
});

test("offers an attribute-free Keycloak client role in both role tabs", async () => {
  const user = setupUser();
  const key = "/api/user-service/coarse-roles/";
  const original = mockCatalog[key] as { roles: unknown[] };
  mockCatalog[key] = {
    roles: [
      ...original.roles,
      {
        id: "b61e5513-cb90-4bd1-908e-d702b4f14404",
        name: "knowledge-tester",
        description: null,
        service_client: "rag-service",
        permissions: [],
        is_builtin: false,
      },
    ],
  };

  try {
    render(<RolesPage />);
    const bundleChoice = screen
      .getAllByText("knowledge-tester")
      .map((text) => text.closest("label"))
      .find((label): label is HTMLLabelElement => label !== null)!;
    expect(within(bundleChoice).getByRole("checkbox")).not.toBeChecked();

    await user.click(
      screen.getByRole("tab", { name: "featureBundlesTabLabel" })
    );
    await user.click(
      screen
        .getAllByText("knowledge-tester")
        .find((text) => text.closest('[role="button"]'))!
        .closest('[role="button"]')!
    );
    expect(
      screen.getByRole("button", { name: "deleteButton" })
    ).toBeInTheDocument();
  } finally {
    mockCatalog[key] = original;
  }
});

test("shows the overview while role distribution is still loading", () => {
  mockDistributionLoading = true;
  render(<RolesPage />);
  expect(screen.getByText("admin.roles.workspaceTitle")).toBeInTheDocument();
  expect(screen.getByText("admin.roles.roleProfilesLabel")).toBeInTheDocument();
  expect(
    screen.getByText("admin.roles.permissionCatalogLabel")
  ).toBeInTheDocument();
  expect(screen.getByText("admin.roles.topRoleLabel")).toBeInTheDocument();
});

test("stages feature bundles by Keycloak ID and submits only on Save", async () => {
  const user = setupUser();
  render(<RolesPage />);

  const checkboxes = await screen.findAllByRole("checkbox");
  const bundleCheckboxes = (name: string) =>
    screen
      .getAllByText(name)
      .map((text) => text.closest("label"))
      .filter((label): label is HTMLLabelElement => label !== null)
      .map((label) => within(label).getByRole("checkbox"));
  const chatChoices = bundleCheckboxes("feature-chat");
  const knowledgeChoices = bundleCheckboxes("feature-knowledge");
  expect(chatChoices.length).toBeGreaterThan(0);
  expect(knowledgeChoices.length).toBeGreaterThan(0);
  expect(checkboxes.length).toBeGreaterThanOrEqual(2);
  chatChoices.forEach((checkbox) => expect(checkbox).toBeChecked());
  knowledgeChoices.forEach((checkbox) => expect(checkbox).not.toBeChecked());

  await user.click(knowledgeChoices[0]!);
  expect(updateCompositeRoleIds).not.toHaveBeenCalled();
  bundleCheckboxes("feature-knowledge").forEach((checkbox) =>
    expect(checkbox).toBeChecked()
  );
  await user.click(chatChoices[0]!);
  expect(updateCompositeRoleIds).not.toHaveBeenCalled();
  bundleCheckboxes("feature-chat").forEach((checkbox) =>
    expect(checkbox).not.toBeChecked()
  );
  await user.click(screen.getByRole("button", { name: "saveButton" }));
  await waitFor(() =>
    expect(updateCompositeRoleIds).toHaveBeenCalledWith(operatorId, {
      role_ids: [knowledgeId],
    })
  );
  expect(updateCompositeRoleIds).toHaveBeenCalledTimes(1);
});

test("shows one client-role selector with full feature-package names", () => {
  render(<RolesPage />);
  expect(
    screen.queryByText("includedServiceRolesTitle")
  ).not.toBeInTheDocument();
  expect(screen.getByText("includedFeatureBundlesTitle")).toBeInTheDocument();
  const roleName = screen.getByText("feature-knowledge");
  expect(roleName).not.toHaveClass("truncate");
  expect(roleName).toHaveClass("whitespace-normal");
  expect(
    within(roleName.closest("label")!).getAllByRole("checkbox")
  ).toHaveLength(1);
});

test("marks assigned client roles on built-in composites with a plain tick", () => {
  const key = "/api/user-service/roles/";
  const original = mockCatalog[key] as {
    roles: Array<Record<string, unknown>>;
  };
  mockCatalog[key] = {
    roles: [{ ...original.roles[0], is_builtin: true }],
  };
  try {
    render(<RolesPage />);
    const assigned = screen.getByText("feature-chat").closest("label")!;
    const unassigned = screen.getByText("feature-knowledge").closest("label")!;
    expect(within(assigned).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(unassigned).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(
      within(assigned).getByRole("img", { name: "assignedFeatureBundleLabel" })
    ).toBeInTheDocument();
    expect(
      within(unassigned).queryByRole("img", {
        name: "assignedFeatureBundleLabel",
      })
    ).not.toBeInTheDocument();
  } finally {
    mockCatalog[key] = original;
  }
});

test("saves feature-package permission checkboxes only after Save", async () => {
  const user = setupUser();
  const catalogKey = "/api/user-service/permissions/";
  const detailKey = `/api/user-service/coarse-roles/${chatId}/permissions`;
  const originalCatalog = mockCatalog[catalogKey];
  mockCatalog[catalogKey] = {
    permissions: ["read", "send"].map((action) => ({
      name: `chat:${action}`,
      label: `Chat ${action}`,
      action,
      entity: "chat",
      feature: "chat",
      service: "agent-service",
      service_client: "agent-service",
    })),
  };
  mockCatalog[detailKey] = { name: "feature-chat", permissions: ["chat:read"] };
  mockMutate.mockImplementation(async (updater) => {
    if (typeof updater === "function") {
      mockCatalog[detailKey] = updater(mockCatalog[detailKey]);
    }
  });
  jest.mocked(updateCoarseRolePermissions).mockResolvedValue({
    ok: true,
    json: async () => ({}),
  } as Response);
  try {
    const { rerender } = render(<RolesPage />);
    await user.click(
      screen.getByRole("tab", { name: "featureBundlesTabLabel" })
    );
    const permission = (label: string) =>
      within(screen.getByText(label).closest("label")!).getByRole("checkbox");
    expect(permission("Chat read")).toBeChecked();
    await user.click(permission("Chat send"));
    rerender(<RolesPage />);
    expect(permission("Chat send")).toBeChecked();
    expect(updateCoarseRolePermissions).not.toHaveBeenCalled();
    expect(mockMutate).toHaveBeenCalledWith(expect.any(Function), {
      revalidate: false,
    });

    // The feature-level select-all checkbox also stages its changes locally.
    const bulk = screen
      .getAllByRole("checkbox")
      .find((box) => !box.closest("label"))!;
    await user.click(bulk);
    rerender(<RolesPage />);
    expect(permission("Chat read")).not.toBeChecked();
    expect(permission("Chat send")).not.toBeChecked();
    expect(updateCoarseRolePermissions).not.toHaveBeenCalled();
    await user.click(permission("Chat send"));
    rerender(<RolesPage />);
    await user.click(screen.getByRole("button", { name: "saveButton" }));
    await waitFor(() =>
      expect(updateCoarseRolePermissions).toHaveBeenCalledWith(chatId, {
        permissions: ["chat:send"],
      })
    );
    expect(updateCoarseRolePermissions).toHaveBeenCalledTimes(1);
    expect(updateCompositeRoleIds).not.toHaveBeenCalled();
  } finally {
    mockCatalog[catalogKey] = originalCatalog;
    delete mockCatalog[detailKey];
    mockMutate.mockReset().mockResolvedValue(undefined);
  }
});

test("shows client permissions and disabled system settings while preserving hidden grants", async () => {
  const user = setupUser();
  const catalogKey = "/api/user-service/permissions/";
  const detailKey = `/api/user-service/coarse-roles/${chatId}/permissions`;
  const ragDetailKey = `/api/user-service/coarse-roles/${knowledgeId}/permissions`;
  const originalCatalog = mockCatalog[catalogKey];
  mockCatalog[catalogKey] = {
    permissions: [
      {
        name: "agent:read",
        label: "Agent read",
        action: "read",
        entity: "shared",
        feature: "system",
        service: "agent-service",
        service_client: "agent-service",
      },
      {
        name: "agent:write",
        label: "Agent write",
        action: "write",
        entity: "shared",
        feature: "system",
        service: "agent-service",
        service_client: "agent-service",
      },
      {
        name: "rag:read",
        label: "RAG read",
        action: "read",
        entity: "shared",
        feature: "system",
        service: "rag-service",
        service_client: "rag-service",
      },
      {
        name: "user:read",
        label: "User read",
        action: "read",
        entity: "user",
        feature: "access",
        service: "user-service",
        service_client: "user-service",
      },
      {
        name: "system.settings:read",
        label: "System settings read",
        action: "read",
        entity: "settings",
        feature: "access",
        service: "system",
        service_client: null,
      },
    ],
  };
  mockCatalog[detailKey] = {
    name: "feature-chat",
    permissions: ["rag:read", "system.settings:read"],
  };
  mockCatalog[ragDetailKey] = { name: "feature-knowledge", permissions: [] };
  mockMutate.mockImplementation(async (updater) => {
    if (typeof updater === "function") {
      mockCatalog[detailKey] = updater(mockCatalog[detailKey]);
    }
  });
  jest.mocked(updateCoarseRolePermissions).mockResolvedValue({
    ok: true,
    json: async () => ({}),
  } as Response);

  try {
    const { rerender } = render(<RolesPage />);
    await user.click(
      screen.getByRole("tab", { name: "featureBundlesTabLabel" })
    );
    const permission = (label: string) =>
      within(screen.getByText(label).closest("label")!).getByRole("checkbox");

    expect(permission("Agent read")).toHaveAttribute("aria-disabled", "false");
    expect(screen.queryByText("RAG read")).not.toBeInTheDocument();
    expect(screen.queryByText("User read")).not.toBeInTheDocument();
    expect(permission("System settings read")).toHaveAttribute(
      "aria-disabled",
      "true"
    );
    expect(permission("System settings read")).toBeChecked();
    expect(
      within(screen.getByText("features.access").parentElement!).getByRole(
        "checkbox"
      )
    ).toHaveAttribute("aria-disabled", "true");
    const featureBulk = within(
      screen.getByText("features.system").parentElement!
    ).getByRole("checkbox");
    await user.click(featureBulk);
    rerender(<RolesPage />);
    expect(permission("Agent read")).toBeChecked();
    expect(permission("Agent write")).toBeChecked();
    expect(permission("System settings read")).toBeChecked();
    await user.click(screen.getByRole("button", { name: "saveButton" }));
    await waitFor(() =>
      expect(updateCoarseRolePermissions).toHaveBeenCalledWith(chatId, {
        permissions: [
          "rag:read",
          "system.settings:read",
          "agent:read",
          "agent:write",
        ],
      })
    );

    await user.click(
      screen
        .getAllByText("feature-knowledge")
        .find((text) => text.closest('[role="button"]'))!
    );
    expect(screen.queryByText("Agent read")).not.toBeInTheDocument();
    expect(permission("RAG read")).toHaveAttribute("aria-disabled", "false");
    expect(permission("System settings read")).toHaveAttribute(
      "aria-disabled",
      "true"
    );
  } finally {
    mockCatalog[catalogKey] = originalCatalog;
    delete mockCatalog[detailKey];
    delete mockCatalog[ragDetailKey];
    mockMutate.mockReset().mockResolvedValue(undefined);
  }
});

test("discards unsaved selections when switching composite roles", async () => {
  const user = setupUser();
  const key = "/api/user-service/roles/";
  const original = mockCatalog[key] as { roles: unknown[] };
  mockCatalog[key] = {
    roles: [
      ...original.roles,
      {
        id: "other-role",
        name: "other-operator",
        permissions: [],
        role_ids: [],
        is_builtin: false,
      },
    ],
  };
  try {
    render(<RolesPage />);
    const choice = () =>
      within(
        screen
          .getAllByText("feature-knowledge")
          .find((text) => text.closest("label"))!
          .closest("label")!
      ).getByRole("checkbox");
    await user.click(choice());
    expect(choice()).toBeChecked();
    await user.click(screen.getByRole("button", { name: /other-operator/ }));
    expect(choice()).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: /custom-operator/ }));
    expect(choice()).not.toBeChecked();
    expect(updateCompositeRoleIds).not.toHaveBeenCalled();
  } finally {
    mockCatalog[key] = original;
  }
});

test("hides platform-role duplicates from feature bundles", async () => {
  const user = setupUser();
  const key = "/api/user-service/coarse-roles/";
  const original = mockCatalog[key];
  mockCatalog[key] = {
    roles: [
      ...(original as { roles: unknown[] }).roles,
      {
        id: "44444444-4444-4444-8444-444444444444",
        name: "custom-operator",
        description: null,
        service_client: "user-service",
        permissions: [],
      },
      {
        id: "66666666-6666-4666-8666-666666666666",
        name: "feature-empty",
        description: null,
        service_client: "user-service",
        permissions: [],
      },
    ],
  };

  try {
    render(<RolesPage />);
    expect(
      screen
        .getAllByText("custom-operator")
        .filter((element) => element.closest("label")?.querySelector("input"))
    ).toHaveLength(0);
    expect(screen.getAllByText("feature-empty").length).toBeGreaterThan(0);

    await user.click(
      screen.getByRole("tab", { name: "featureBundlesTabLabel" })
    );
    expect(screen.queryByText("custom-operator")).not.toBeInTheDocument();
    expect(screen.getAllByText("feature-empty").length).toBeGreaterThan(0);
    expect(screen.getAllByText("feature-chat").length).toBeGreaterThan(0);
  } finally {
    mockCatalog[key] = original;
  }
});

test("refreshes all identity catalog reads and selected details without a sync POST", async () => {
  const user = setupUser();
  render(<RolesPage />);
  await user.click(screen.getByRole("button", { name: "refreshButton" }));
  await waitFor(() => expect(mockRefresh).toHaveBeenCalledTimes(1));
  const [matches, data, options] = mockRefresh.mock.calls[0]!;
  expect(data).toBeUndefined();
  expect(options).toEqual({ revalidate: true, throwOnError: true });
  for (const key of [
    "/api/user-service/roles/",
    "/api/user-service/coarse-roles/",
    "/api/user-service/permissions/",
    `/api/user-service/roles/${operatorId}/role-ids`,
    `/api/user-service/roles/${operatorId}/permissions`,
    `/api/user-service/coarse-roles/${chatId}/permissions`,
  ])
    expect(matches(key)).toBe(true);
  expect(matches("/api/user-service/users/")).toBe(false);
  expect(updateCompositeRoleIds).not.toHaveBeenCalled();
});

test("shows the selected role's Keycloak ID on the role page", async () => {
  render(<RolesPage />);

  expect(await screen.findByText("roleIdLabel")).toBeInTheDocument();
  expect(screen.getByText(operatorId)).toBeInTheDocument();
});

test("creates a role and selects it by its new Keycloak ID", async () => {
  const user = setupUser();
  jest.mocked(createCompositeRole).mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "44444444-4444-4444-8444-444444444444",
      name: "auditor",
    }),
  } as Response);
  render(<RolesPage />);

  await user.click(screen.getByRole("button", { name: "newRoleButton" }));
  await user.type(
    screen.getByPlaceholderText("compositeRoleNamePlaceholder"),
    "auditor"
  );
  await user.click(
    screen.getByRole("button", { name: "createCompositeRoleTitle" })
  );

  await waitFor(() =>
    expect(createCompositeRole).toHaveBeenCalledWith({
      name: "auditor",
      description: "",
    })
  );
});

test.each([
  [
    { status: "ready", distribution: [{ role: "enduser", count: 5 }] },
    "enduser · 5",
  ],
  [{ status: "pending", distribution: [] }, "admin.roles.topRoleCalculating"],
  [
    { status: "unavailable", distribution: [] },
    "admin.roles.topRoleUnavailable",
  ],
])(
  "renders the most used role from the distribution snapshot",
  (body, text) => {
    mockCatalog["/api/user-service/users/role-distribution"] = {
      ...body,
      computed_at: null,
    };
    render(<RolesPage />);
    expect(screen.getByText(text)).toBeInTheDocument();
    delete mockCatalog["/api/user-service/users/role-distribution"];
  }
);
