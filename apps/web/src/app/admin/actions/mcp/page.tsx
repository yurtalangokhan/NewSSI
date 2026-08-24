"use client";

import MCPPageContent from "@/sections/actions/MCPPageContent";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import useMcpServers from "@/hooks/useMcpServers";
import { MCPServerStatus } from "@/lib/tools/interfaces";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.MCP_ACTIONS]!;

export default function Main() {
  const { t } = useTranslation();
  const { mcpData, isLoading } = useMcpServers();
  const mcpServers = mcpData?.mcp_servers ?? [];
  const connectedServers = mcpServers.filter(
    (server) => server.status === MCPServerStatus.CONNECTED
  ).length;
  const toolCount = mcpServers.reduce(
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
              value: isLoading ? "..." : String(mcpServers.length),
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
          actions={[
            {
              label: t("admin.navigation.routes.agents.sidebar", {
                defaultValue: "Agents",
              }),
              href: ADMIN_PATHS.AGENTS,
              primary: true,
            },
          ]}
        />
        <MCPPageContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
