import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(
  request: Request,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  try {
    const { chatSessionId } = await params;
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        `/api/chat/stop-chat-session/${chatSessionId}`
      ).toString(),
      {
        method: "POST",
        headers: {
          ...(cookie ? { Cookie: cookie } : {}),
        },
      }
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to stop chat session" },
      { status: 500 }
    );
  }
}
