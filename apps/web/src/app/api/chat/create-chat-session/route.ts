import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";
import { parseResponseModel } from "@/lib/api/responseModel";
import { FetchError } from "@/lib/api/http/errors";
import { errorResponseFromException } from "@/lib/api/errorResponse";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const response = await proxyToBackend(
      request,
      chatEndpoints.createSession.backend,
      { method: "POST" }
    );
    if (!response.ok) return response;
    const envelope = await response.clone().json();
    const data = await parseResponseModel<Record<string, unknown>>(response);
    const id = data?.chat_session_id ?? data?.id ?? data?.chatSessionId;
    if (typeof id !== "string" || !id) {
      throw new FetchError("Invalid create chat session response", 502, null);
    }
    const headers = new Headers(response.headers);
    headers.delete("content-length");
    return NextResponse.json(
      { ...envelope, data: { ...data, chat_session_id: id, id } },
      {
        status: response.status,
        headers,
      }
    );
  } catch (error) {
    if (error instanceof FetchError) {
      return NextResponse.json(
        {
          statusCode: error.status,
          message: error.userMessage,
          data: null,
          error: { code: error.code, message: error.userMessage },
        },
        { status: error.status }
      );
    }
    return errorResponseFromException(error, request);
  }
}
