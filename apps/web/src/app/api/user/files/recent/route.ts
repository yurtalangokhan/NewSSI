import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, projectsEndpoints.recentFiles.backend);
}
