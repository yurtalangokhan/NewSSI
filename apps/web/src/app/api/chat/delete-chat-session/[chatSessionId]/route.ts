import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: Request, { params }: { params: Promise<{ chatSessionId: string }> }) {
  try {
    const { chatSessionId } = await params;
    const response = await fetch(`${INTERNAL_URL}/api/chat/delete-chat-session/${chatSessionId}`, {
      method: "POST",
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to delete chat session" }, { status: 500 });
  }
}
