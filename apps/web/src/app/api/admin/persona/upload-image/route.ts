import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const cookie = request.headers.get("cookie") || "";
    const authorization = request.headers.get("authorization");
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/admin/persona/upload-image"
      ).toString(),
      {
        method: "POST",
        body: formData,
        headers: {
          ...(cookie ? { Cookie: cookie } : {}),
          ...(authorization ? { Authorization: authorization } : {}),
        },
      }
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to upload image" },
      { status: 500 }
    );
  }
}
