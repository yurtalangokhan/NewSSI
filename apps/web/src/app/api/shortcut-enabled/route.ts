import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextRequest, NextResponse } from "next/server";
import { appSettings } from "@/lib/settings";

export async function PATCH(request: NextRequest) {
  const enabled =
    request.nextUrl.searchParams.get("shortcut_enabled") === "true";
  const response = await backendRequest({
    ...preferencesEndpoints.updateShortcutEnabled().backend,
    request,
    method: "PATCH",
    body: JSON.stringify({ shortcut_enabled: enabled }),
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
