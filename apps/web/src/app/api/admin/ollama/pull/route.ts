import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    const cookie = request.headers.get("cookie");
    if (cookie) {
      headers["Cookie"] = cookie;
    }
    const upstream = await fetch(`${INTERNAL_URL}/api/admin/ollama/pull`, {
      method: "POST",
      body,
      headers,
    });

    if (!upstream.body) {
      return NextResponse.json({ error: "No body" }, { status: 500 });
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "text/event-stream" },
    });
  } catch {
    return NextResponse.json({ error: "Failed" }, { status: 500 });
  }
}
