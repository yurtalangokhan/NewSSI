import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(request: Request) {
  try {
    // Proxy to backend which calls LangGraph's /threads/search
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(`${INTERNAL_URL}/api/chat/get-user-chat-sessions`, {
      headers: {
        ...(cookie ? { Cookie: cookie } : {}),
      },
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to fetch chat sessions:', error);
    return NextResponse.json({ sessions: [], chat_sessions: [], has_more: false }, { status: 200 });
  }
}
