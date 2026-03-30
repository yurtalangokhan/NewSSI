import { NextRequest, NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

// LangGraph SDK proxy - maps SDK calls to agent-service endpoints
// SDK calls: /threads/search, /threads/{id}, /threads/{id}/state, etc.

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // Remove /api/langgraph from the path
    const path = pathname.replace('/api/langgraph', '');
    
    const response = await fetch(`${INTERNAL_URL}${path}${url.search}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('LangGraph proxy GET error:', error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // Remove /api/langgraph from the path
    const path = pathname.replace('/api/langgraph', '');
    
    const body = await request.text();

    const response = await fetch(`${INTERNAL_URL}${path}`, {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Handle streaming responses
    if (response.headers.get('content-type')?.includes('text/event-stream')) {
      return new NextResponse(response.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('LangGraph proxy POST error:', error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // Remove /api/langgraph from the path
    const path = pathname.replace('/api/langgraph', '');
    
    const body = await request.text();

    const response = await fetch(`${INTERNAL_URL}${path}`, {
      method: 'PATCH',
      body,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('LangGraph proxy PATCH error:', error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const pathname = url.pathname;
    
    // Remove /api/langgraph from the path
    const path = pathname.replace('/api/langgraph', '');

    const response = await fetch(`${INTERNAL_URL}${path}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('LangGraph proxy DELETE error:', error);
    return NextResponse.json({ error: "Proxy error" }, { status: 500 });
  }
}
