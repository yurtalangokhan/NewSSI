import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ fileId: string }> }
) {
  try {
    const { fileId } = await params;
    
    // For now, return a mock file not found response
    // In production, this would proxy to actual file storage
    return NextResponse.json({ 
      error: "File not found",
      file_id: fileId 
    }, { status: 404 });
  } catch (error) {
    return NextResponse.json({ error: "Failed to fetch file" }, { status: 500 });
  }
}
