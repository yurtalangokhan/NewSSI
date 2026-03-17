import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function PUT(request: Request) {
  try {
    const body = await request.text();
    const response = await fetch(`${INTERNAL_URL}/api/chat/set-message-as-latest`, {
      method: "PUT",
      body,
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to set message as latest" }, { status: 500 });
  }
}
