import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    const cookie = _request.headers.get("cookie") || "";

    // No authenticated context: avoid noisy backend 401 logs.
    if (!cookie) {
      return NextResponse.json([]);
    }

    // Proxy to backend files endpoint
    const response = await fetch(`${INTERNAL_URL}/user/projects/session/${sessionId}/files`, {
      headers: {
        Cookie: cookie,
      },
    });

    if (!response.ok) {
      return NextResponse.json([], { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (_error) {
    return NextResponse.json([]);
  }
}
