import { NextResponse } from 'next/server';

export async function POST() {
  return NextResponse.json({ chat_session_id: "new-session-1", name: "New Chat" });
}
