import { NextRequest, NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || 'http://localhost:8123';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ fileId: string }> }
) {
  try {
    const { fileId } = await params;
    const backendUrl = `${INTERNAL_URL}/api/chat/file/${encodeURIComponent(fileId)}`;

    const headers: Record<string, string> = {};
    const cookie = request.headers.get('cookie');
    if (cookie) headers['Cookie'] = cookie;
    const auth = request.headers.get('authorization');
    if (auth) headers['Authorization'] = auth;

    const response = await fetch(backendUrl, { headers, cache: 'no-store' });

    if (!response.ok) {
      return NextResponse.json({ error: 'File not found' }, { status: response.status });
    }

    const contentType = response.headers.get('Content-Type') || 'application/octet-stream';
    const body = await response.arrayBuffer();

    return new Response(body, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'private, max-age=3600',
        ...(response.headers.get('Content-Disposition')
          ? { 'Content-Disposition': response.headers.get('Content-Disposition')! }
          : {}),
      },
    });
  } catch {
    return NextResponse.json({ error: 'Failed to fetch file' }, { status: 500 });
  }
}
