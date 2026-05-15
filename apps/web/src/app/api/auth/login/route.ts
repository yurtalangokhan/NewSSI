import { NextRequest } from 'next/server';
import { proxyToBackend } from '@/lib/api/proxy';
import { USER_SERVICE_URL } from "@/lib/constants";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, '/api/auth/login', {
    method: 'GET',
    backendUrl: USER_SERVICE_URL,
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, '/api/auth/login', {
    method: 'POST',
    backendUrl: USER_SERVICE_URL,
  });
}
