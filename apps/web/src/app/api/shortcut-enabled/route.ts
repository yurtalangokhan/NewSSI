import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(request: NextRequest) {
  const enabled =
    request.nextUrl.searchParams.get("shortcut_enabled") === "true";
  const response = await fetch(
    buildServiceUrl(
      USER_SERVICE_URL,
      "user",
      "/api/users/me/settings/"
    ).toString(),
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Cookie: request.headers.get("cookie") || "",
        ...getLanguageHeaders(request),
        ...(request.headers.get("authorization")
          ? { Authorization: request.headers.get("authorization") || "" }
          : {}),
      },
      body: JSON.stringify({ shortcut_enabled: enabled }),
    }
  );

  return new NextResponse(await response.text(), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
