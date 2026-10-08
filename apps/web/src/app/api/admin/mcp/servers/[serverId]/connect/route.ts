import { NextRequest } from "next/server";
import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ serverId: string }> }
) {
  const { serverId } = await params;
  return proxyToBackend(
    request,
    toolsEndpoints.connectMcpServer(serverId).backend,
    { method: "POST" }
  );
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ serverId: string }> }
) {
  const { serverId } = await params;
  return proxyToBackend(
    request,
    toolsEndpoints.disconnectMcpServer(serverId).backend,
    { method: "DELETE" }
  );
}
