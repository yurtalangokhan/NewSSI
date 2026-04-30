import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: Request, { params }: { params: Promise<{ chatSessionId: string }> }) {
  try {
    const { chatSessionId } = await params;
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(`${INTERNAL_URL}/api/chat/stop-chat-session/${chatSessionId}`, {
      method: "POST",
      headers: {
        ...(cookie ? { Cookie: cookie } : {}),
      },
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to stop chat session" }, { status: 500 });
  }
}
