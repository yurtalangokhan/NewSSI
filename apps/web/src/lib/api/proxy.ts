import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.INTERNAL_URL || 'http://localhost:8080';

export interface ProxyOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  withCredentials?: boolean;
}

/**
 * Proxy a request to the backend API
 */
export async function proxyToBackend(
  request: NextRequest,
  pathname: string,
  options: ProxyOptions = {}
): Promise<NextResponse> {
  try {
    const { method = request.method, withCredentials = true } = options;
    
    // Build URL with query params
    const url = new URL(`${BACKEND_URL}${pathname}`);
    if (request.nextUrl.search) {
      url.search = request.nextUrl.search;
    }

    const headers: HeadersInit = {
      'Content-Type': request.headers.get('content-type') || 'application/json',
    };

    if (withCredentials) {
      const cookie = request.headers.get('cookie');
      if (cookie) {
        headers['Cookie'] = cookie;
      }
    }

    let body: string | undefined;
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      body = await request.text();
    }

    const response = await fetch(url.toString(), {
      method,
      headers,
      body,
    });

    const responseText = await response.text();
    const result = new NextResponse(responseText, {
      status: response.status,
      statusText: response.statusText,
    });

    // Copy headers
    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== 'content-encoding') {
        result.headers.set(key, value);
      }
    });

    // Forward set-cookie headers
    response.headers.getSetCookie().forEach(cookie => {
      result.headers.append('Set-Cookie', cookie);
    });

    return result;
  } catch (error) {
    console.error(`Proxy error for ${pathname}:`, error);
    return NextResponse.json(
      { error: 'Backend service unavailable' },
      { status: 503 }
    );
  }
}
