import { cookies } from "next/headers";
import { appSettings } from "@/lib/settings";

interface CookieStore {
  getAll(): { name: string; value: string }[];
}

export function serializeServerCookies(cookieStore: CookieStore): string {
  let cookieHeader = cookieStore
    .getAll()
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");

  if (
    appSettings.DEBUG_AUTH_COOKIE &&
    appSettings.NODE_ENV === "development"
  ) {
    const hasAuthCookie = cookieHeader
      .split(/;\s*/)
      .some((cookie) => cookie.startsWith("fastapiusersauth="));
    if (!hasAuthCookie) {
      const debugCookie = `fastapiusersauth=${appSettings.DEBUG_AUTH_COOKIE}`;
      cookieHeader = cookieHeader
        ? `${cookieHeader}; ${debugCookie}`
        : debugCookie;
    }
  }

  return cookieHeader;
}

export async function getServerRequestHeaders(
  headers?: HeadersInit
): Promise<Record<string, string>> {
  const result = Object.fromEntries(new Headers(headers).entries());
  result.cookie = serializeServerCookies(await cookies());
  return result;
}
