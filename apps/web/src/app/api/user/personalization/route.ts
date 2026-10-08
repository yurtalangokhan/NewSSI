import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { getDerivedIncomingIdempotencyHeaders } from "@/lib/api/idempotency";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(request: NextRequest) {
  const payload = await request.json();
  if (typeof payload.name === "string") {
    const [firstName, ...rest] = payload.name
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    const profileResponse = await backendRequest({
      ...preferencesEndpoints.updatePersonalizationProfile.backend,
      request,
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...(await getDerivedIncomingIdempotencyHeaders(request, "profile")),
      },
      body: JSON.stringify({
        first_name: firstName || null,
        last_name: rest.join(" ") || null,
      }),
    });
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
    return NextResponse.json({
      statusCode: 200,
      message: null,
      data: { ok: true },
      error: null,
    });
  }

  const response = await backendRequest({
    ...preferencesEndpoints.updatePersonalizationSettings.backend,
    request,
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(await getDerivedIncomingIdempotencyHeaders(request, "settings")),
    },
    body: JSON.stringify(settingsPayload),
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
