import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const response = await fetch(
      `${INTERNAL_URL}/api/admin/providers/test-connection`,
      {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
      }
    );
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: "Failed" }, { status: 500 });
  }
}
