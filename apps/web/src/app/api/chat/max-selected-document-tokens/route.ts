import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({ max_tokens: 120000, selected_tokens: 120000 });
}
