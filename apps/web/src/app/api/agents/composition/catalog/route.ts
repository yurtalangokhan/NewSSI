import { proxyToBackend } from "@/lib/api/proxy";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, agentsEndpoints.compositionCatalog.backend);
}
