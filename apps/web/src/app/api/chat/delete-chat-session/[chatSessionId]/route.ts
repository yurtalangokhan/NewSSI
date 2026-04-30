import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  try {
    const { chatSessionId } = await params;
    const response = await fetch(`${INTERNAL_URL}/api/chat/delete-chat-session/${chatSessionId}`, {
      method: "DELETE",
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to delete chat session:', error);
    return NextResponse.json({ success: false, error: "Failed to delete chat session" }, { status: 500 });
  }
}

// Also support POST for backward compatibility
export async function POST(
  request: Request,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  return DELETE(request, { params });
}
