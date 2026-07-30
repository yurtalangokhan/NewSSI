import { buildServiceUrl } from "@/lib/api/gatewayRouting";

export function buildPublicUserAuthUrl(path: string): URL {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = buildServiceUrl(
    process.env.USER_SERVICE_URL || "http://localhost:8090",
    "user",
    `/api/auth${normalizedPath}`
  );
  url.search = "";
  url.hash = "";
  return url;
}
