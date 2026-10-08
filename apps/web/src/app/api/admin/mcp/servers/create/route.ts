import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  return proxyToBackend(request, toolsEndpoints.adminServersCreate.backend, {
    method: "POST",
  });
}
