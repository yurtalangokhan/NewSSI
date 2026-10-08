import {
  BUILTIN_MCP_SERVER_ID,
  isBuiltinMcpServer,
  isRegisteredMcpProvider,
} from "./mcpUtils";
import { MCPServerStatus } from "./interfaces";
import type { MCPServer } from "./interfaces";

function server(status: MCPServerStatus): MCPServer {
  return {
    id: 2,
    name: "Deneme",
    server_url: "https://www.deneme.com",
    owner: "system",
    is_authenticated: true,
    status,
    tool_count: 0,
  };
}

describe("isRegisteredMcpProvider", () => {
  it("hides a CREATED row so registering one does not look like adding it", () => {
    expect(isRegisteredMcpProvider(server(MCPServerStatus.CREATED))).toBe(true);
  });

  it.each([
    MCPServerStatus.CONNECTED,
    MCPServerStatus.AWAITING_AUTH,
    MCPServerStatus.DISCONNECTED,
    MCPServerStatus.FETCHING_TOOLS,
  ])("keeps an added (%s) provider visible", (status) => {
    expect(isRegisteredMcpProvider(server(status))).toBe(false);
  });
});

describe("isBuiltinMcpServer", () => {
  it("recognises the platform's own tools server by its reserved id", () => {
    expect(
      isBuiltinMcpServer({
        ...server(MCPServerStatus.CONNECTED),
        id: BUILTIN_MCP_SERVER_ID,
      })
    ).toBe(true);
  });

  it("treats every other server as an external provider", () => {
    expect(isBuiltinMcpServer(server(MCPServerStatus.CONNECTED))).toBe(false);
  });
});
