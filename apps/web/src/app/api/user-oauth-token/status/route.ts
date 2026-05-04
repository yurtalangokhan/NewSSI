import { NextResponse } from "next/server";

export async function GET() {
  // Compatibility endpoint: this backend does not expose per-user OAuth token
  // status yet, so return an empty list to avoid noisy 404s.
  return NextResponse.json([]);
}
