import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_URL } from "@/lib/constants";

const BACKEND_URL = INTERNAL_URL;

export interface ProxyOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  withCredentials?: boolean;
  backendUrl?: string;
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
    const {
      method = request.method,
      withCredentials = true,
      backendUrl = BACKEND_URL,
    } = options;
    
    // Build URL with query params
    const url = new URL(`${backendUrl}${pathname}`);
    if (request.nextUrl.search) {
      url.search = request.nextUrl.search;
    }

    const headers: HeadersInit = {
      'Content-Type': request.headers.get('content-type') || 'application/json',
    };

    const authorization = request.headers.get('authorization');
    if (authorization) {
      headers['Authorization'] = authorization;
    }

    if (withCredentials) {
      let cookie = request.headers.get('cookie') || '';
      if (
        process.env.DEBUG_AUTH_COOKIE &&
        process.env.NODE_ENV === 'development' &&
        !cookie.split(/;\s*/).some((c) => c.startsWith('fastapiusersauth='))
      ) {
        const debugCookie = `fastapiusersauth=${process.env.DEBUG_AUTH_COOKIE}`;
        cookie = cookie ? `${cookie}; ${debugCookie}` : debugCookie;
      }
      if (cookie) {
        headers['Cookie'] = cookie;
      }
    }

    let body: BodyInit | undefined;
    if (['POST', 'PUT', 'PATCH'].includes(method)) {
      body = await request.arrayBuffer();
    }

    const response = await fetch(url.toString(), {
      method,
      headers,
      body,
    });

    const noContent = new Set([204, 205, 304]).has(response.status);
    const responseText = noContent ? "" : await response.text();
    const result = new NextResponse(noContent ? null : responseText, {
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
