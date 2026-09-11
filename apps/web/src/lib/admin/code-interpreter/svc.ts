import { authenticatedFetch } from "@/lib/fetcher";
const UPDATE_ENDPOINT = "/api/admin/code-interpreter";

interface CodeInterpreterUpdateRequest {
  enabled: boolean;
}

export async function updateCodeInterpreter(
  request: CodeInterpreterUpdateRequest
): Promise<Response> {
  return authenticatedFetch(UPDATE_ENDPOINT, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
