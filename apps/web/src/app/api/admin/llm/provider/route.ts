import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    providers: [],
    selected_provider: null,
  });
}
