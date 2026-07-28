import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function DELETE(request: Request) {
  try {
    const body = await request.text();
    const response = await fetch(`${INTERNAL_URL}/api/chat/remove-chat-message-feedback`, {
      method: "DELETE",
      body,
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to remove feedback" }, { status: 500 });
  }
}
