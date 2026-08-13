import { proxyToBackend } from "@/lib/api/proxy";
import { AGENT_CATALOG_API_PATH } from "@/lib/agents/apiPaths";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, AGENT_CATALOG_API_PATH);
}
