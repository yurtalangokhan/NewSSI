import { proxyToBackend } from "@/lib/api/proxy";
import { buildAgentDetailApiPath } from "@/lib/agents/apiPaths";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ agentId: string }> }
) {
  const { agentId } = await params;
  return proxyToBackend(request, buildAgentDetailApiPath(agentId));
}
