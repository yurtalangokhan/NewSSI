import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    success: true,
    user_id: "dev-user-1"
  });
}

export async function POST() {
  return NextResponse.json({
    success: true,
    user_id: "dev-user-1"
  });
}
