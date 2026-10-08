import { isRegisteredMcpProvider } from "@/lib/tools/mcpUtils";
import type {
  MCPAuthenticationPerformer,
  MCPAuthenticationType,
  MCPServer,
} from "@/lib/tools/interfaces";

export interface SavedAuthChoice {
  auth_type: MCPAuthenticationType;
  auth_performer: MCPAuthenticationPerformer;
}

/**
 * The authentication a server was actually configured with, or `null` when
 * there is none to honour. A provider that was only registered carries the
 * backend default (`NONE`), which means "not chosen yet", so the form keeps
 * its own default instead of jumping to it once the detail loads.
 */
export function savedAuthChoice(
  server: MCPServer | undefined
): SavedAuthChoice | null {
  if (!server || isRegisteredMcpProvider(server)) return null;
  return {
    auth_type: server.auth_type as MCPAuthenticationType,
    auth_performer: server.auth_performer as MCPAuthenticationPerformer,
  };
}
