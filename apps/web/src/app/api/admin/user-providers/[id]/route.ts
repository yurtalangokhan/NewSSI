import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(
    request,
    modelProvidersEndpoints.updateUserProvider(id).backend,
    {
      method: "PUT",
    }
  );
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(
    request,
    modelProvidersEndpoints.deleteUserProvider(id).backend,
    {
      method: "DELETE",
    }
  );
}
