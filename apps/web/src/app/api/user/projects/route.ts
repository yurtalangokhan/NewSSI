import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

/**
 * Proxy GET /api/user/projects to agent-service
 * Forwards auth headers to ensure fallback resolution works in dev mode
 */
export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/api/user/projects");
}

/**
 * Proxy POST /api/user/projects to agent-service
 */
export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/user/projects", {
    method: "POST",
  });
}

/**
 * Proxy PATCH /api/user/projects to agent-service
 */
export async function PATCH(request: NextRequest) {
  return proxyToBackend(request, "/api/user/projects", {
    method: "PATCH",
  });
}

/**
 * Proxy DELETE /api/user/projects to agent-service
 */
export async function DELETE(request: NextRequest) {
  return proxyToBackend(request, "/api/user/projects", {
    method: "DELETE",
  });
}
