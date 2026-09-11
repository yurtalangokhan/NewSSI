import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { getDerivedIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(request: NextRequest) {
  const payload = await request.json();
  const baseHeaders = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
    ...getLanguageHeaders(request),
    ...(request.headers.get("authorization")
      ? { Authorization: request.headers.get("authorization") || "" }
      : {}),
  };

  if (typeof payload.name === "string") {
    const [firstName, ...rest] = payload.name
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    const profileResponse = await fetch(
      buildServiceUrl(USER_SERVICE_URL, "user", "/api/users/me").toString(),
      {
        method: "PATCH",
        headers: {
          ...baseHeaders,
          ...(await getDerivedIncomingIdempotencyHeaders(request, "profile")),
        },
        body: JSON.stringify({
          first_name: firstName || null,
          last_name: rest.join(" ") || null,
        }),
      }
    );
    if (!profileResponse.ok) {
      return new NextResponse(await profileResponse.text(), {
        status: profileResponse.status,
        statusText: profileResponse.statusText,
        headers: profileResponse.headers,
      });
    }
  }

  const settingsPayload: Record<string, unknown> = {};
  if ("role" in payload) {
    settingsPayload.work_role = payload.role;
  }
  if ("memories" in payload) {
    settingsPayload.memories = payload.memories;
  }
  if ("long_term_memory_enabled" in payload) {
    settingsPayload.long_term_memory_enabled = payload.long_term_memory_enabled;
  }
  if ("extract_memory" in payload) {
    settingsPayload.extract_memory = payload.extract_memory;
  }
  if ("user_preferences" in payload) {
    settingsPayload.user_preferences = payload.user_preferences;
  }

  if (Object.keys(settingsPayload).length === 0) {
    return NextResponse.json({ ok: true });
  }

  const response = await fetch(
    buildServiceUrl(
      USER_SERVICE_URL,
      "user",
      "/api/users/me/settings/"
    ).toString(),
    {
      method: "PATCH",
      headers: {
        ...baseHeaders,
        ...(await getDerivedIncomingIdempotencyHeaders(request, "settings")),
      },
      body: JSON.stringify(settingsPayload),
    }
  );

  return new NextResponse(await response.text(), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
