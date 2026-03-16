import { NextResponse } from 'next/server';

export async function POST() {
  return NextResponse.json(
    { error: "Streaming not implemented in mock mode" },
    {
      headers: {
        'Content-Type': 'text/event-stream',
      }
    }
  );
}
