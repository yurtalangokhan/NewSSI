import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const cookie = request.headers.get("cookie") || "";

    // No authenticated context: avoid noisy backend 401 logs.
    if (!cookie) {
      return NextResponse.json({ token_count: 0, total_tokens: 0 });
    }

    // Proxy to backend token-count endpoint
    const response = await fetch(`${INTERNAL_URL}/user/projects/session/${sessionId}/token-count`, {
      headers: {
        Cookie: cookie,
      },
    });

    if (!response.ok) {
      return NextResponse.json({ token_count: 0, total_tokens: 0 }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    // Return mock data for now
    return NextResponse.json({ token_count: 0, total_tokens: 0 });
  }
}
