import {
  buildMcpOnlyToolSelectionGroups,
  buildToolSelectionGroups,
  countSelectedTools,
  SelectableMcpTool,
} from "@/refresh-components/agents/McpToolSelectionCard";
import { MCPServer, MCPServerStatus } from "@/lib/tools/interfaces";

function tool(overrides: Partial<SelectableMcpTool>): SelectableMcpTool {
  return {
    name: "tool",
    display_name: "Tool",
    description: "",
    mcp_server_id: null,
    enabled: true,
    agent_creation_selectable: true,
    ...overrides,
  };
}

function server(overrides: Partial<MCPServer>): MCPServer {
  return {
    id: 1,
    name: "Server",
    server_url: "https://server.example",
    owner: "admin",
    is_authenticated: true,
    status: MCPServerStatus.CONNECTED,
    tool_count: 1,
    ...overrides,
  };
}

describe("McpToolSelectionCard helpers", () => {
  test("groups external MCP tools by server and service tools by category", () => {
    const groups = buildToolSelectionGroups({
      mcpTools: [
        tool({ id: 10, name: "github_search", mcp_server_id: 7 }),
        tool({ id: 11, name: "github_issue", mcp_server_id: 7 }),
      ],
      mcpServers: [server({ id: 7, name: "GitHub" })],
      serviceToolsByCategory: {
        browser: [tool({ id: 20, name: "open_url", display_name: "Open URL" })],
      },
      categoryLabelMap: { browser: "Browser" },
    });

    expect(groups).toEqual([
      expect.objectContaining({
        id: "mcp-7",
        title: "GitHub",
        tools: expect.arrayContaining([
          expect.objectContaining({ name: "github_search" }),
          expect.objectContaining({ name: "github_issue" }),
        ]),
      }),
      expect.objectContaining({
        id: "service-browser",
        title: "Browser",
        tools: [expect.objectContaining({ name: "open_url" })],
      }),
    ]);
  });

  test("counts selected tools that are present in groups", () => {
    const groups = buildToolSelectionGroups({
      mcpTools: [tool({ id: 10, name: "github_search", mcp_server_id: 7 })],
      mcpServers: [server({ id: 7, name: "GitHub" })],
      serviceToolsByCategory: {
        browser: [tool({ id: 20, name: "open_url" })],
      },
      categoryLabelMap: { browser: "Browser" },
    });

    expect(countSelectedTools(groups, ["github_search", "missing"])).toBe(1);
  });

  test("builds agent groups from MCP server tools only", () => {
    const groups = buildMcpOnlyToolSelectionGroups({
      tools: [
        tool({ id: 10, name: "github_search", mcp_server_id: 7 }),
        tool({ id: 20, name: "image_generation", mcp_server_id: null }),
        tool({ id: 21, name: "open_url", mcp_server_id: undefined }),
      ],
      mcpServers: [server({ id: 7, name: "GitHub" })],
    });

    expect(groups).toEqual([
      expect.objectContaining({
        id: "mcp-7",
        title: "GitHub",
        tools: [expect.objectContaining({ name: "github_search" })],
      }),
    ]);
  });
});

describe("countSelectedTools with nested children", () => {
  test("counts tools inside nested children groups", () => {
    const groups = [
      {
        id: "builtin-root",
        title: "Built-in Tools",
        children: [
          {
            id: "service-docker",
            title: "Docker",
            tools: [{ name: "docker_ps" }],
          },
          { id: "service-fs", title: "Files", tools: [{ name: "read_file" }] },
        ],
      },
      {
        id: "mcp-1001",
        title: "Microsoft",
        tools: [{ name: "get_recent_azure_updates" }],
      },
    ];

    expect(
      countSelectedTools(groups, [
        "docker_ps",
        "get_recent_azure_updates",
        "nope",
      ])
    ).toBe(2);
  });
});
