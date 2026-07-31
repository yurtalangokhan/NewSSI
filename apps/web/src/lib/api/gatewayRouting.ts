export type BackendService = "agent" | "rag" | "tools" | "user";

const SERVICE_PREFIX: Record<BackendService, string> = {
  agent: "agent-service",
  rag: "rag-service",
  tools: "tools-service",
  user: "user-service",
};

function trimSlashes(value: string): string {
  return value.replace(/^\/+|\/+$/g, "");
}

function withLeadingSlash(value: string): string {
  return value.startsWith("/") ? value : `/${value}`;
}

function isGatewayUrl(url: URL, service: BackendService): boolean {
  const firstSegment = trimSlashes(url.pathname).split("/")[0];
  return (
    url.hostname === "kong" ||
    url.port === "8000" ||
    firstSegment === SERVICE_PREFIX[service]
  );
}

function serviceScopedBase(baseUrl: string, service: BackendService): URL {
  const url = new URL(baseUrl);
  const baseSegments = trimSlashes(url.pathname)
    .split("/")
    .filter(Boolean);
  const prefix = SERVICE_PREFIX[service];

  if (isGatewayUrl(url, service) && baseSegments[0] !== prefix) {
    baseSegments.unshift(prefix);
  }

  url.pathname = baseSegments.length ? `/${baseSegments.join("/")}` : "/";
  url.search = "";
  url.hash = "";
  return url;
}

export function canonicalServicePath(
  service: BackendService,
  path: string
): string {
  const normalizedPath = withLeadingSlash(path);

  if (service === "tools") {
    return normalizedPath.startsWith("/mcp") ? normalizedPath : "/mcp";
  }

  if (service === "agent" && normalizedPath.startsWith("/mcp/")) {
    return `/api/v1/proxy${normalizedPath}`;
  }

  if (normalizedPath.startsWith("/api/v1/")) {
    return normalizedPath;
  }

  if (normalizedPath === "/api/v1") {
    return normalizedPath;
  }

  if (normalizedPath.startsWith("/api/")) {
    return `/api/v1${normalizedPath.slice(4)}`;
  }

  return `/api/v1${normalizedPath}`;
}

export function buildServiceUrl(
  baseUrl: string,
  service: BackendService,
  path: string
): URL {
  const url = serviceScopedBase(baseUrl, service);
  const basePath = trimSlashes(url.pathname);
  const canonicalPath = canonicalServicePath(service, path);
  const hasTrailingSlash =
    canonicalPath.endsWith("/") && canonicalPath !== "/";
  const apiPath = trimSlashes(canonicalPath);
  url.pathname = `/${[basePath, apiPath].filter(Boolean).join("/")}`;
  if (hasTrailingSlash && !url.pathname.endsWith("/")) {
    url.pathname += "/";
  }
  return url;
}
