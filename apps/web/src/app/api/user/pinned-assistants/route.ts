import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function PATCH(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(`${INTERNAL_URL}/api/user/pinned-assistants`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Failed to update pinned assistants:', error);
    return NextResponse.json({ error: "Failed to update pinned assistants" }, { status: 500 });
  }
}

export async function GET() {
  try {
    const response = await fetch(`${INTERNAL_URL}/api/user/pinned-assistants`);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    // Return empty array for dev mode
    return NextResponse.json({ pinned_assistants: [] });
  }
}
