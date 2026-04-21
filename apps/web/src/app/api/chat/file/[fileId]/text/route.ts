import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || 'http://localhost:8123';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ fileId: string }> }
) {
  try {
    const { fileId } = await params;
    const backendUrl = `${INTERNAL_URL}/api/chat/file/${encodeURIComponent(fileId)}/text`;

    const response = await fetch(backendUrl, { cache: 'no-store' });

    if (!response.ok) {
      return NextResponse.json({ error: 'Failed to extract text' }, { status: response.status });
    }

    const text = await response.text();
    return new Response(text, {
      status: 200,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    });
  } catch {
    return NextResponse.json({ error: 'Failed to fetch file text' }, { status: 500 });
  }
}
