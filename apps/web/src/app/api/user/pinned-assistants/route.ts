import { USER_SERVICE_URL } from "@/lib/constants";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextRequest, NextResponse } from "next/server";

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Cookie: request.headers.get("cookie") || "",
    };
    const auth = request.headers.get("authorization");
    if (auth) headers["Authorization"] = auth;

    const response = await fetch(
      buildServiceUrl(
        USER_SERVICE_URL,
        "user",
        "/api/users/me/settings/"
      ).toString(),
      {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          pinned_assistants: body.ordered_assistant_ids || [],
        }),
      }
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Failed to update pinned assistants:", error);
    return NextResponse.json(
      { error: "Failed to update pinned assistants" },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Cookie: request.headers.get("cookie") || "",
    };
    const auth = request.headers.get("authorization");
    if (auth) headers["Authorization"] = auth;

    const response = await fetch(
      buildServiceUrl(
        USER_SERVICE_URL,
        "user",
        "/api/users/me/settings/"
      ).toString(),
      {
        headers,
      }
    );
    const data = await response.json();
    return NextResponse.json({
      pinned_assistants: data.pinned_assistants || [],
    });
  } catch (error) {
    return NextResponse.json({ pinned_assistants: [] });
  }
}
