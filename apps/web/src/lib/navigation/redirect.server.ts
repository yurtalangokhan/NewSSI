import { NextRequest } from "next/server";
import { appSettings } from "@/lib/settings";

export const getDomain = (request: NextRequest) => {
  if (appSettings.NODE_ENV !== "production") {
    return request.nextUrl.origin;
  }

  // Never trust X-Forwarded-* headers from the request — they can be spoofed by
  // an attacker to poison redirect URLs (host header poisoning). WEB_DOMAIN is
  // required rather than optional precisely so production has no branch that
  // falls back to a request-derived origin.
  return appSettings.HOST_URL;
};
