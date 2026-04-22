import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  try {
    const { personaId } = await params;
    const response = await fetch(`${INTERNAL_URL}/api/persona/${personaId}`);
    if (!response.ok) {
      return NextResponse.json({ error: "Persona not found" }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to fetch persona" }, { status: 500 });
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  try {
    const { personaId } = await params;
    const body = await request.text();
    const response = await fetch(`${INTERNAL_URL}/api/persona/${personaId}`, {
      method: "PATCH",
      body,
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json({ error: "Failed to update persona" }, { status: 500 });
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ personaId: string }> }) {
  try {
    const { personaId } = await params;
    const response = await fetch(`${INTERNAL_URL}/api/persona/${personaId}`, {
      method: "DELETE",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json({ error: "Failed to delete persona" }, { status: 500 });
  }
}
