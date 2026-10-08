import {
  FetchError,
  parseApiErrorPayload,
  parseApiErrorResponse,
} from "@/lib/api/http/errors";

/** JSON contract for backend endpoints migrated to ResponseModel. */
export interface ResponseModel<T> {
  statusCode: number;
  message: string | null;
  data: T | null;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    field_errors?: Array<{ field: string; code: string; message: string }>;
    request_id?: string | null;
  } | null;
}

export function unwrapResponseModel<T>(result: ResponseModel<T>): T {
  if (
    !result ||
    typeof result !== "object" ||
    !Number.isInteger(result.statusCode) ||
    !("data" in result)
  ) {
    const error = parseApiErrorPayload(null, 502);
    throw new FetchError(error.userMessage, 502, result, error);
  }
  if (result.statusCode < 200 || result.statusCode >= 300 || result.error) {
    const error = parseApiErrorPayload(result, result.statusCode);
    throw new FetchError(error.userMessage, result.statusCode, result, error);
  }
  return result.data as T;
}

export async function parseResponseModel<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.clone().json();
    } catch {
      // Legacy text and unreadable errors still use the shared error parser.
    }
    if (
      payload &&
      typeof payload === "object" &&
      "statusCode" in payload &&
      payload.statusCode !== response.status
    ) {
      const error = parseApiErrorPayload(null, 502);
      throw new FetchError(error.userMessage, 502, payload, error);
    }
    const error = await parseApiErrorResponse(response);
    throw new FetchError(error.userMessage, response.status, error.raw, error);
  }
  let result: ResponseModel<T>;
  try {
    result = (await response.json()) as ResponseModel<T>;
  } catch {
    const error = parseApiErrorPayload(null, 502);
    throw new FetchError(error.userMessage, 502, null, error);
  }
  if (result?.statusCode !== response.status) {
    const error = parseApiErrorPayload(null, 502);
    throw new FetchError(error.userMessage, 502, error.raw, error);
  }
  return unwrapResponseModel(result);
}
