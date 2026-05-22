import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

/**
 * Catch-all proxy for /api/user/projects/[...path]
 * Handles routes like:
 * - POST /api/user/projects/create
 * - GET /api/user/projects/{projectId}
 * - PATCH /api/user/projects/{projectId}
 * - DELETE /api/user/projects/{projectId}
 * - POST /api/user/projects/{projectId}/move_chat_session
 * - POST /api/user/projects/remove_chat_session
 * etc.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const pathStr = (await params).path.join("/");
  return proxyToBackend(request, `/api/user/projects/${pathStr}`);
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const pathStr = (await params).path.join("/");
  return proxyToBackend(request, `/api/user/projects/${pathStr}`, {
    method: "POST",
  });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const pathStr = (await params).path.join("/");
  return proxyToBackend(request, `/api/user/projects/${pathStr}`, {
    method: "PATCH",
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const pathStr = (await params).path.join("/");
  return proxyToBackend(request, `/api/user/projects/${pathStr}`, {
    method: "DELETE",
  });
}
