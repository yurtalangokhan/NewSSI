import { proxyToBackend } from '@/lib/api/proxy';
import { USER_SERVICE_URL } from '@/lib/constants';
import { NextRequest } from 'next/server';

export async function GET(request: NextRequest) {
  return proxyToBackend(request, '/api/auth/me', {
    method: 'GET',
    withCredentials: true,
    backendUrl: USER_SERVICE_URL,
  });
}
