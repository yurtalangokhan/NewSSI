import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ serverId: string }> }
) {
  const { serverId } = await params;
  return proxyToBackend(
    request,
    toolsEndpoints.getMcpServerDetails(serverId).backend
  );
}
