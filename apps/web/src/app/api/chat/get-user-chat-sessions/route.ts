import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({ chat_sessions: [], sessions: [] });
}
