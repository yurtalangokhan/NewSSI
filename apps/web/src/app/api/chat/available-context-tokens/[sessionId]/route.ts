import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    const { sessionId } = await params;
    // Proxy to backend available-context-tokens endpoint
    const response = await fetch(`${INTERNAL_URL}/api/chat/available-context-tokens/${sessionId}`);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    // Return mock data for now
    return NextResponse.json({ max_tokens: 120000, selected_tokens: 120000 });
  }
}
