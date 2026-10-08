import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ modelName: string[] }> }
) {
  return proxyToBackend(
    request,
    modelProvidersEndpoints.deleteOllamaModel(
      (await props.params).modelName.join("/")
    ).backend,
    { method: "DELETE" }
  );
}
