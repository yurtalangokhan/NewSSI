import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

type RouteContext = { params: Promise<{ serverId: string }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { serverId } = await context.params;
  return proxyToBackend(
    request,
    toolsEndpoints.getMcpServerTools(serverId).backend
  );
}
