/**
 * mail_configs_route.py's /api/mail-configs surface (list/create configs,
 * available configs, user-credentials, per-config test/send/delete) had no
 * matching Next.js route, so a client-side fetch to it fell through to
 * next.config.js's generic `/api/:path*` rewrite -- a raw proxy that
 * forwards the browser's request unchanged. The browser only carries the
 * access_token as an httpOnly cookie; agent-service deliberately never
 * reads cookies (bearer-token only), so every one of those requests got a
 * 401 no matter how valid the session was, and authenticatedFetch's
 * retry-after-refresh got 401 again and forced a logout. proxyToBackend
 * reads that cookie server-side and attaches it as an Authorization
 * header, same as every other backend surface already does.
 *
 * `[[...path]]` (optional catch-all) so the base `/api/mail-configs` path
 * itself -- no segments, used by list/create -- also matches.
 */
import { proxyToBackend } from "@/lib/api/proxy";
import { systemEndpoints } from "@/lib/api/domains/system/endpoints";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(
    request,
    systemEndpoints.mailConfigsProxyTarget((await props.params).path).backend
  );
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(
    request,
    systemEndpoints.mailConfigsProxyTarget((await props.params).path).backend,
    { method: "POST" }
  );
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(
    request,
    systemEndpoints.mailConfigsProxyTarget((await props.params).path).backend,
    { method: "PUT" }
  );
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(
    request,
    systemEndpoints.mailConfigsProxyTarget((await props.params).path).backend,
    { method: "PATCH" }
  );
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(
    request,
    systemEndpoints.mailConfigsProxyTarget((await props.params).path).backend,
    { method: "DELETE" }
  );
}
