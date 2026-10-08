import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.getAdminProvider.backend
  );
}

export async function PUT(request: NextRequest) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.updateAdminProvider.backend,
    {
      method: "PUT",
    }
  );
}

export async function POST(request: NextRequest) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.createAdminProvider.backend,
    {
      method: "POST",
    }
  );
}
