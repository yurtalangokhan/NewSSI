import {
  ADMIN_PATHS,
  ADMIN_ROUTE_CONFIG,
  canAccessAdminPanel,
  getFirstAccessibleAdminPath,
  getAdminRouteConfigForPathname,
  sidebarItem,
} from "../admin-routes";
import { hasAllPermissions } from "@/lib/auth/permissions";
import i18n from "@/i18n/config";
import { readdirSync } from "node:fs";
import { join } from "node:path";

describe("admin route permissions", () => {
  it("grants admin-panel entry when an enabled route is accessible", () => {
    expect(ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]?.enabled).not.toBe(false);
    expect(
      hasAllPermissions(
        ["agent:view"],
        ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]?.requiredPermissions
      )
    ).toBe(true);
    expect(canAccessAdminPanel(["agent:view"])).toBe(true);
    expect(canAccessAdminPanel(["user:view"])).toBe(true);
  });

  it("denies admin-panel entry without permissions for an enabled route", () => {
    expect(canAccessAdminPanel(["chat:send"])).toBe(false);
    expect(canAccessAdminPanel([])).toBe(false);
  });

  it("supports wildcard admin-panel access", () => {
    expect(canAccessAdminPanel(["*"])).toBe(true);
  });

  it("selects an admin landing page the user can access", () => {
    expect(getFirstAccessibleAdminPath(["user:view"])).toBe(ADMIN_PATHS.USERS);
  });

  it("requires explicit role view access for the roles page", () => {
    expect(ADMIN_ROUTE_CONFIG[ADMIN_PATHS.ROLES]?.requiredPermissions).toEqual([
      "role:view",
    ]);
  });

  it("includes permission requirements in sidebar items", () => {
    expect(sidebarItem(ADMIN_PATHS.USERS).requiredPermissions).toEqual([
      "user:view",
    ]);
  });

  it("registers mail configs under configuration permissions", () => {
    expect(
      ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MAIL_CONFIGS]?.requiredPermissions
    ).toEqual(["mail_config:view"]);
  });

  it("gates the MCP configuration page on its own configure permission", () => {
    const required =
      ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MCP_CONFIG]?.requiredPermissions;
    expect(required).toEqual(["mcp_provider:configure"]);
    // A system admin holds configure (via the wildcard grant).
    expect(hasAllPermissions(["*"], required)).toBe(true);
    expect(hasAllPermissions(["mcp_provider:configure"], required)).toBe(true);
    // An enterprise admin connects providers but never configures them, even
    // if a legacy grant left them with the registry write permissions.
    expect(
      hasAllPermissions(
        [
          "mcp_provider:read",
          "mcp_provider:connect",
          "mcp_provider:create",
          "mcp_provider:update",
        ],
        required
      )
    ).toBe(false);
  });

  it("supports filtering sidebar items by all required permissions", () => {
    const items = [
      sidebarItem(ADMIN_PATHS.USERS),
      sidebarItem(ADMIN_PATHS.ROLES),
    ];

    const visible = items.filter((item) =>
      hasAllPermissions(["role:view"], item.requiredPermissions)
    );

    expect(visible.map((item) => item.link)).toEqual([ADMIN_PATHS.ROLES]);
  });

  it("resolves nested admin pages to the nearest route permission config", () => {
    expect(
      getAdminRouteConfigForPathname("/admin/users/add")?.requiredPermissions
    ).toEqual(["user:view"]);
    expect(
      getAdminRouteConfigForPathname("/admin/documents/sets/new")
        ?.requiredPermissions
    ).toEqual(["collection:view"]);
  });

  it("localizes the organizations sidebar label", async () => {
    await i18n.changeLanguage("en");
    expect(sidebarItem(ADMIN_PATHS.ORGANIZATIONS, i18n.t).name).toBe(
      "Organization"
    );

    await i18n.changeLanguage("tr");
    expect(sidebarItem(ADMIN_PATHS.ORGANIZATIONS, i18n.t).name).toBe(
      "Organizasyon"
    );

    await i18n.changeLanguage("en");
  });
});

it("opens organization management with the organization view permission", () => {
  expect(getFirstAccessibleAdminPath(["org:view"])).toBe(
    ADMIN_PATHS.ORGANIZATIONS
  );
});

it("does not treat normal application permissions as admin page access", () => {
  expect(
    canAccessAdminPanel([
      "agent:list",
      "agent:read",
      "datasource:read",
      "mcp_tool:read",
      "provider:read",
      "org:read",
      "user:list",
      "settings:read",
    ])
  ).toBe(false);
});

it("requires explicit view permissions for every configured admin page", () => {
  for (const config of Object.values(ADMIN_ROUTE_CONFIG)) {
    expect(config.requiredPermissions?.length).toBeGreaterThan(0);
    expect(config.requiredPermissions?.every((p) => p.endsWith(":view"))).toBe(
      true
    );
  }
});

it.each([
  ["/admin/connector/123", "datasource:view"],
  ["/admin/connectors/postgres", "datasource_add:view"],
  ["/admin/federated/123", "datasource:view"],
  ["/admin/actions/new", "mcp_tool:view"],
  ["/admin/actions/edit-mcp", "mcp_tool:view"],
  ["/admin/embeddings", "embedding:view"],
])("protects direct navigation to %s", (path, permission) => {
  expect(getAdminRouteConfigForPathname(path)?.requiredPermissions).toEqual([
    permission,
  ]);
});

it("covers every existing admin page, including dynamic and callback routes", () => {
  function pages(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory()
        ? pages(path)
        : entry.name === "page.tsx"
          ? [path]
          : [];
    });
  }
  const appRoot = join(process.cwd(), "src/app");
  for (const file of pages(join(appRoot, "admin"))) {
    const route = file
      .slice(appRoot.length)
      .replaceAll("\\", "/")
      .replace(/\/page\.tsx$/, "");
    expect(getAdminRouteConfigForPathname(route)?.requiredPermissions).toEqual([
      expect.stringMatching(/:view$/),
    ]);
  }
});
