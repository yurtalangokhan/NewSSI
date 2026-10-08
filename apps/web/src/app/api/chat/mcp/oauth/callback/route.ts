import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { NextRequest, NextResponse } from "next/server";
import { deriveIdempotencyKey } from "@/lib/api/idempotency";
import { backendRequest } from "@/lib/api/http/server";
import { validateInternalRedirect } from "@/lib/auth/redirectValidation";

// Proxies browser callback to backend OAuth callback endpoint and then
// redirects back to the chat UI.

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const serverId =
    url.searchParams.get("server_id") || url.searchParams.get("serverId");
  const codeVerifier = url.searchParams.get("code_verifier");

  if (!code || !serverId) {
    return NextResponse.json(
      { error: "Missing code or server_id" },
      { status: 400 }
    );
  }

  try {
    const resp = await backendRequest({
      ...toolsEndpoints.oauthCallback().backend,
      request: req,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": await deriveIdempotencyKey(
          code,
          "mcp-oauth-callback"
        ),
      },
      body: JSON.stringify({
        server_id: serverId,
        code,
        state,
        code_verifier: codeVerifier,
        transport: "streamable-http",
      }),
      credentials: "include",
      deriveAuthorizationFromCookie: true,
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}) as any);
      return NextResponse.json(
        { error: err.detail || "OAuth callback failed" },
        { status: 400 }
      );
    }

    // Check if this is an admin OAuth flow
    const isAdminFlow = url.searchParams.get("admin") === "true";

    // Redirect back to appropriate page. redirect_to is caller-supplied, so
    // it goes through validateInternalRedirect the same way logout's next=
    // does -- an unvalidated value here is a GET-triggerable open redirect.
    let redirectTo = validateInternalRedirect(
      url.searchParams.get("redirect_to")
    );
    if (!redirectTo) {
      if (isAdminFlow) {
        // For admin flow, redirect back to the MCP edit page
        redirectTo = `/admin/actions/edit-mcp?server_id=${serverId}`;
      } else {
        // For user flow, redirect to chat
        redirectTo = "/app";
      }
    }

    return NextResponse.redirect(new URL(redirectTo, req.url));
  } catch (e) {
    return NextResponse.json(
      { error: "OAuth callback error" },
      { status: 500 }
    );
  }
}
