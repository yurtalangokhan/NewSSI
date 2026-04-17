import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET() {
  try {
    const response = await fetch(`${INTERNAL_URL}/api/persona`);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to fetch personas" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const response = await fetch(`${INTERNAL_URL}/api/persona`, {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json({ error: "Failed to create persona" }, { status: 500 });
  }
}
