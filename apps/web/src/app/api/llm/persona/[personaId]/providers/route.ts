import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

interface RouteContext {
  params: Promise<{ personaId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { personaId } = await params;
  return proxyToBackend(
    request,
    modelProvidersEndpoints.getPersonaProviders(personaId).backend
  );
}
