/**
 * proxy_route.py's /api/proxy/* surface (built-in MCP tool listing/execution,
 * Ollama models, RAG collections) had no matching Next.js route, so a
 * client-side fetch to it fell through to next.config.js's generic
 * `/api/:path*` rewrite -- a raw proxy that forwards the browser's request
 * unchanged. The browser only carries the access_token as an httpOnly
 * cookie; agent-service deliberately never reads cookies (bearer-token
 * only), so every one of those requests got a 401 no matter how valid the
 * session was, and authenticatedFetch's retry-after-refresh got 401 again
 * and forced a logout. proxyToBackend reads that cookie server-side and
 * attaches it as an Authorization header, same as every other backend
 * surface already does.
 */
import { proxyToBackend } from "@/lib/api/proxy";
import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.proxyResourceTarget((await props.params).path).backend
  );
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.proxyResourceTarget((await props.params).path).backend,
    { method: "POST" }
  );
}
