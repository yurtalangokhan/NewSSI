import { NextResponse } from "next/server";

// File upload is handled client-side (base64 inline in the message payload).
// A separate server-side upload endpoint is no longer needed.
export async function POST() {
  return NextResponse.json(
    {
      error:
        "Use inline base64 file_descriptors in the message payload instead.",
    },
    { status: 405 }
  );
}
