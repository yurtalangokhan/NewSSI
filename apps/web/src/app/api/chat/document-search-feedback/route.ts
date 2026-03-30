import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    
    // Proxy document search feedback to backend
    // For now, return success
    return NextResponse.json({ 
      success: true,
      feedback: body,
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to submit feedback" }, { status: 500 });
  }
}
