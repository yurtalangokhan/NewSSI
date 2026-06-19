import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(request: NextRequest) {
  const enabled =
    request.nextUrl.searchParams.get("shortcut_enabled") === "true";
  const response = await fetch(`${USER_SERVICE_URL}/api/users/me/settings/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Cookie: request.headers.get("cookie") || "",
      ...(request.headers.get("authorization")
        ? { Authorization: request.headers.get("authorization") || "" }
        : {}),
    },
    body: JSON.stringify({ shortcut_enabled: enabled }),
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}
