import { parseResponseModel } from "@/lib/api/responseModel";
import { FetchError } from "@/lib/api/http/errors";

/**
 * Decode user-service JSON at a domain boundary while retaining the Response
 * interface used by existing mutations. Redirects and files stay transport
 * responses. Components receive the original payload rather than the envelope.
 */
export async function userServicePayloadResponse(
  response: Response
): Promise<Response> {
  if (response.status >= 300 && response.status < 400) return response;
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  try {
    const data = await parseResponseModel<unknown>(response);
    return new Response(JSON.stringify(data), {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  } catch (error) {
    if (!(error instanceof FetchError)) throw error;
    return new Response(
      JSON.stringify({
        message: error.message,
        detail: error.message,
        error: { code: error.code, message: error.message },
      }),
      { status: error.status || 502, headers }
    );
  }
}
