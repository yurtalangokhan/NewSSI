import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, modelProvidersEndpoints.listProviders.backend);
}

export async function POST(request: NextRequest) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.createProvider.backend,
    {
      method: "POST",
    }
  );
}
