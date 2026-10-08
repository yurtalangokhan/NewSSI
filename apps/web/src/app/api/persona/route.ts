import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, agentsEndpoints.listPersonas.backend);
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, agentsEndpoints.createPersona.backend, {
    method: "POST",
  });
}
