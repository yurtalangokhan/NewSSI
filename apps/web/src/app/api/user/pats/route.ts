import { NextResponse } from "next/server";

export async function GET() {
  // Compatibility endpoint: PAT APIs are not available in this backend.
  return NextResponse.json([]);
}

export async function POST() {
  return NextResponse.json(
    { detail: "PAT API is not supported in this deployment." },
    { status: 501 }
  );
}
