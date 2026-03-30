import { NextResponse } from 'next/server';

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

export async function POST(request: Request) {
  try {
    // Proxy file upload to backend
    // For now, return a mock response since file handling isn't implemented
    const formData = await request.formData();
    const file = formData.get('file');
    
    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }
    
    // Generate a mock file ID
    const fileId = `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    return NextResponse.json({
      file_id: fileId,
      file_name: file instanceof File ? file.name : "unknown",
      status: "uploaded",
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to upload file" }, { status: 500 });
  }
}
