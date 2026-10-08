import { SOURCE_METADATA_MAP } from "../sources";
import { DatabaseIcon, FileIcon } from "@/components/icons/icons";
import type { IconProps } from "@opal/types";
import { SvgServer } from "@opal/icons";
import { MCPServer, MCPServerStatus } from "./interfaces";

/** Id agent-service reserves for the platform's own built-in tools server. */
export const BUILTIN_MCP_SERVER_ID = 1;

/** The built-in tools server is not a registered provider and has no connection to manage. */
export function isBuiltinMcpServer(server: MCPServer): boolean {
  return server.id === BUILTIN_MCP_SERVER_ID;
}

/**
 * A provider a system admin registered on the configuration page but that no
 * one has added on the actions page yet.
 *
 * The two pages mean different things: the configuration page *registers* a
 * URL in the catalog, and the actions page *adds* a server (picking it from
 * that catalog and connecting it). Adding is what moves a provider out of
 * `CREATED`, so a `CREATED` row must be offered in the "Add MCP server" picker
 * but must not render as a card — otherwise registering a URL looks like
 * adding a server.
 */
export function isRegisteredMcpProvider(server: MCPServer): boolean {
  return server.status === MCPServerStatus.CREATED;
}

/**
 * Get an appropriate icon for an MCP server based on its URL and name.
 * Leverages the existing SOURCE_METADATA_MAP for connector icons.
 */
export function getActionIcon(
  serverUrl: string | undefined,
  serverName: string | undefined
): React.FunctionComponent<IconProps> {
  // Handle undefined/null inputs
  const url = (serverUrl || "").toLowerCase();
  const name = (serverName || "").toLowerCase();

  for (const [sourceKey, metadata] of Object.entries(SOURCE_METADATA_MAP)) {
    const keyword = sourceKey.toLowerCase();

    if (url.includes(keyword) || name.includes(keyword)) {
      const Icon = metadata.icon;
      return Icon;
    }
  }

  if (
    url.includes("postgres") ||
    url.includes("mysql") ||
    url.includes("mongodb") ||
    url.includes("redis")
  ) {
    return DatabaseIcon;
  }
  if (url.includes("filesystem") || name.includes("file system")) {
    return FileIcon;
  }

  return SvgServer;
}
