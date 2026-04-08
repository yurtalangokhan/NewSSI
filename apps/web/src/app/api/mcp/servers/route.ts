import { NextResponse } from 'next/server';

const TOOLS_SERVICE_URL = process.env.TOOLS_SERVICE_URL || "http://localhost:8002/mcp";

export async function GET() {
  // Return the tools-service as a default MCP server
  // The actual tools are fetched from /api/proxy/mcp/tools-builtin
  return NextResponse.json({
    mcp_servers: [
      {
        id: 1,
        name: "tools-service",
        description: "Built-in tools from tools-service",
        server_url: TOOLS_SERVICE_URL,
        transport: "streamable_http",
      }
    ]
  });
}
