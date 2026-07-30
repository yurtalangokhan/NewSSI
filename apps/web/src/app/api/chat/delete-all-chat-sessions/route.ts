import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function DELETE(request: Request) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/chat/delete-all-chat-sessions"
      ).toString(),
      {
        method: "DELETE",
        headers: {
          ...(cookie ? { Cookie: cookie } : {}),
        },
      }
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("Failed to delete all chat sessions:", error);
    return NextResponse.json(
      { success: false, error: "Failed to delete all chat sessions" },
      { status: 500 }
    );
  }
}

// Also support POST for backward compatibility
export async function POST(request: Request) {
  return DELETE(request);
}
