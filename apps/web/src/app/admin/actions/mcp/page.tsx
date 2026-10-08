"use client";

import MCPPageContent from "@/sections/actions/MCPPageContent";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/navigation/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { useMcpServers } from "@/lib/api/domains/tools/hooks";
import { MCPServer, MCPServerStatus } from "@/lib/tools/interfaces";
import { isRegisteredMcpProvider } from "@/lib/tools/mcpUtils";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MCP_ACTIONS]!;

export default function Main() {
  const { t } = useTranslation();
  const { mcpData, isLoading } = useMcpServers();
  const mcpServers = (mcpData?.mcp_servers ?? []) as MCPServer[];
  // A provider only registered on the config page is not an added server, so it
  // is neither listed nor counted here (it lives in the "Add MCP server" picker).
  const visibleServers = mcpServers.filter(
    (server) => !isRegisteredMcpProvider(server)
  );
  const connectedServers = visibleServers.filter(
    (server) => server.status === MCPServerStatus.CONNECTED
  ).length;
  const toolCount = visibleServers.reduce(
    (total, server) => total + (server.tool_count ?? 0),
    0
  );

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={t("admin.actions.mcpDescription")}
        separator
      />
      <SettingsLayouts.Body>
        <AdminOverviewPanel
          icon={route.icon}
          isLoading={isLoading}
          title={t("admin.actions.mcpWorkspaceTitle", {
            defaultValue: "Action workspace",
          })}
          description={t("admin.actions.mcpWorkspaceDescription", {
            defaultValue:
              "Connect MCP servers, inspect available tools, and decide what agents can safely use.",
          })}
          metrics={[
            {
              label: t("admin.actions.serversLabel"),
              value: isLoading ? "..." : String(visibleServers.length),
            },
            {
              label: t("admin.actions.connectedServersLabel"),
              value: isLoading ? "..." : String(connectedServers),
              tone: connectedServers > 0 ? "success" : "warning",
            },
            {
              label: t("admin.actions.toolsLabel"),
              value: isLoading ? "..." : String(toolCount),
            },
          ]}
        />
        <MCPPageContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
