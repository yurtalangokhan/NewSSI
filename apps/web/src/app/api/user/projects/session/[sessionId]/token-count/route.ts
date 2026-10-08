import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  return proxyToBackend(
    request,
    projectsEndpoints.getSessionTokenCount(sessionId).backend
  );
}
