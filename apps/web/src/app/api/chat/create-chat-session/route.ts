import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const response = await proxyToBackend(
      request,
      "/api/chat/create-chat-session",
      {
        method: "POST",
      }
    );
    const data = await response.json();
    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }
    const normalizedChatSessionId =
      data?.chat_session_id ?? data?.id ?? data?.chatSessionId ?? null;

    if (!normalizedChatSessionId) {
      return NextResponse.json(
        { error: "Invalid create chat session response" },
        { status: 502 }
      );
    }

    return NextResponse.json({
      ...data,
      chat_session_id: normalizedChatSessionId,
      id: normalizedChatSessionId,
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to create chat session" },
      { status: 500 }
    );
  }
}
