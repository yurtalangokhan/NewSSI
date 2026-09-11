import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

type RouteContext = { params: Promise<{ serverId: string }> };

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { serverId } = await context.params;
  return proxyToBackend(request, `/api/admin/mcp/server/${serverId}/status`, {
    method: "PATCH",
  });
}
