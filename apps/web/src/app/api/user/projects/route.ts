import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

/**
 * Proxy GET /api/user/projects to agent-service
 * Forwards auth headers to ensure fallback resolution works in dev mode
 */
export async function GET(request: NextRequest) {
  return proxyToBackend(request, projectsEndpoints.listProjects.backend);
}

/**
 * Proxy POST /api/user/projects to agent-service
 */
export async function POST(request: NextRequest) {
  return proxyToBackend(request, projectsEndpoints.createProject.backend, {
    method: "POST",
  });
}

/**
 * Proxy PATCH /api/user/projects to agent-service
 */
export async function PATCH(request: NextRequest) {
  return proxyToBackend(request, projectsEndpoints.updateProject.backend, {
    method: "PATCH",
  });
}

/**
 * Proxy DELETE /api/user/projects to agent-service
 */
export async function DELETE(request: NextRequest) {
  return proxyToBackend(request, projectsEndpoints.deleteProject.backend, {
    method: "DELETE",
  });
}
