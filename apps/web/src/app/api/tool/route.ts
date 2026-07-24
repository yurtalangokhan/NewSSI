import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function GET() {
  try {
    const response = await fetch(`${INTERNAL_URL}/mcp/tools-builtin`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      return NextResponse.json([]);
    }

    const data = await response.json();
    const tools = Array.isArray(data?.tools) ? data.tools : [];

    return NextResponse.json(
      tools.map((tool: { name?: string; description?: string }) => ({
        id: 0,
        name: tool.name || '',
        display_name: (tool.name || '').replace(/[_-]/g, ' '),
        description: tool.description || '',
        definition: null,
        custom_headers: [],
        in_code_tool_id: tool.name || null,
        passthrough_auth: false,
        oauth_config_id: null,
        oauth_config_name: null,
        mcp_server_id: null,
        user_id: null,
        enabled: true,
        chat_selectable: true,
        agent_creation_selectable: true,
        default_enabled: false,
      }))
    );
  } catch {
    return NextResponse.json([]);
  }
}
