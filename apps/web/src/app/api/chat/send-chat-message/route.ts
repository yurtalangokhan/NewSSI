import { NextRequest, NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const cookie = request.headers.get("cookie") || "";
    
    // Call the backend send-chat-message endpoint which handles:
    // 1. Session creation/updates
    // 2. Thread creation in LangGraph store
    // 3. Message storage
    // 4. Streaming response
    const url = `${INTERNAL_URL}/api/chat/send-chat-message`;
    
    const response = await fetch(url, {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        ...(cookie ? { Cookie: cookie } : {}),
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, details: errorText },
        { status: response.status }
      );
    }

    // Stream the response back to the client
    const stream = response.body;
    if (!stream) {
      return NextResponse.json(
        { error: 'No response body' },
        { status: 500 }
      );
    }

    // Return the streaming response with proper headers
    return new Response(stream, {
      status: response.status,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',  // Disable nginx buffering
      },
    });
  } catch (error) {
    console.error('Chat proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to send chat message', details: String(error) },
      { status: 500 }
    );
  }
}
