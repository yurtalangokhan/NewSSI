import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function DELETE(request: Request) {
  try {
    const cookie = request.headers.get("cookie") || "";
    const response = await fetch(`${INTERNAL_URL}/api/chat/delete-all-chat-sessions`, {
      method: "DELETE",
      headers: {
        ...(cookie ? { Cookie: cookie } : {}),
      },
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to delete all chat sessions:', error);
    return NextResponse.json({ success: false, error: "Failed to delete all chat sessions" }, { status: 500 });
  }
}

// Also support POST for backward compatibility
export async function POST(request: Request) {
  return DELETE(request);
}
