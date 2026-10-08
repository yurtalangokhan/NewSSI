import { systemEndpoints } from "@/lib/api/domains/system/endpoints";
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";

export function GET(request: NextRequest) {
  return proxyToBackend(request, systemEndpoints.version.backend);
}
