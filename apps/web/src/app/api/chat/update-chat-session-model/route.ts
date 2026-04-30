import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function PUT(request: Request) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(`${INTERNAL_URL}/api/chat/update-chat-session-model`, {
      method: "PUT",
      body,
      headers: {
        "Content-Type": "application/json",
        ...(cookie ? { Cookie: cookie } : {}),
      }
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to update chat session model" }, { status: 500 });
  }
}
