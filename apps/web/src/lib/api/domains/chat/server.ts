import { parseResponseModel } from "@/lib/api/responseModel";
import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";

import type { BackendChatSession } from "./types";

async function fetchChatSessionResponse(
  chatId: string,
  query?: Record<string, string>
): Promise<Response> {
  return backendRequest({
    ...chatEndpoints.getSession(chatId).backend,
    query,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
}

export async function fetchBackendChatSessionSS(
  chatId: string
): Promise<BackendChatSession | null> {
  const response = await fetchChatSessionResponse(chatId);
  if (!response.ok) return null;
  return await parseResponseModel<BackendChatSession>(response);
}

export async function fetchSharedChatSS(
  chatId: string
): Promise<BackendChatSession | null> {
  const response = await fetchChatSessionResponse(chatId, {
    is_shared: "True",
  });
  return response.ok
    ? await parseResponseModel<BackendChatSession>(response)
    : null;
}
