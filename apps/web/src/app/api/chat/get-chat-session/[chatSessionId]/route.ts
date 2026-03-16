import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    chat_session_id: "test-session",
    name: "Test Chat",
    messages: [],
  });
}
