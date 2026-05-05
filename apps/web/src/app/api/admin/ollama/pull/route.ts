import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const upstream = await fetch(`${INTERNAL_URL}/api/admin/ollama/pull`, {
      method: "POST",
      body,
      headers: {
        "Content-Type": "application/json",
        Authorization: request.headers.get("Authorization") || "",
      },
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
