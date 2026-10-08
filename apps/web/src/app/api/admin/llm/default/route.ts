import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.setDefaultModel.backend,
    {
      method: "POST",
    }
  );
}
