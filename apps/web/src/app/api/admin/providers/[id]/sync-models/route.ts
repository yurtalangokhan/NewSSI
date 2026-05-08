import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const response = await fetch(
      `${INTERNAL_URL}/api/admin/providers/${id}/sync-models`,
      {
        method: "POST",
        headers: { Authorization: request.headers.get("Authorization") || "" },
      }
    );
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: "Failed" }, { status: 500 });
  }
}
