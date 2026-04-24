import { NextResponse } from 'next/server';

const LANGCONNECT_URL = process.env.LANGCONNECT_URL || "http://localhost:8083";

export async function GET() {
  try {
    const response = await fetch(`${LANGCONNECT_URL}/datasources/knowledge-selector`);
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { document_processing: [], knowledge_graph: [] },
      { status: 500 }
    );
  }
}
