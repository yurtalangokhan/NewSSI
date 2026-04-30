import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: Request) {
  try {
    const requestBody = await request.json().catch(() => ({}));
    const response = await fetch(`${INTERNAL_URL}/api/chat/create-chat-session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requestBody),
    });
    const data = await response.json();
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
    return NextResponse.json({ error: "Failed to create chat session" }, { status: 500 });
  }
}
