import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(
    request,
    modelProvidersEndpoints.syncProviderModels(id).backend,
    {
      method: "POST",
    }
  );
}
