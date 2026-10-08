/**
 * Route prefixes APISIX exposes for the backend services. A service URL that
 * carries none of them reaches Gateway but matches no route.
 */
export const GATEWAY_ROUTE_PREFIXES = [
  "/agent-service",
  "/user-service",
  "/rag-service",
  "/tools-service",
  "/internal/agent-service",
  "/internal/user-service",
  "/internal/rag-service",
  "/internal/tools-service",
] as const;

function hasGatewayRoutePrefix(pathname: string): boolean {
  const path = pathname.replace(/\/+$/, "");
  return GATEWAY_ROUTE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`)
  );
}

/**
 * Reject any service URL that would bypass Gateway.
 *
 * Backend services no longer authenticate callers themselves — Gateway does,
 * and forwards the result as trusted headers. A URL pointing straight at a
 * service host therefore does not just skip route authorization, it fails with
 * 401 on every request. Catch that here, at boot, with a message that names the
 * variable, rather than at runtime as a wall of unexplained 401s.
 */
export function assertGatewayRouted(
  name: string,
  value: string,
  gatewayUrl: string
): void {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error(
      `${name} must be an absolute URL, got ${JSON.stringify(value)}`
    );
  }

  const gateway = new URL(gatewayUrl);
  if (url.origin !== gateway.origin) {
    throw new Error(
      `${name}=${value} does not point at Gateway (${gateway.origin}). ` +
        `Every service call must go through Gateway; a direct service URL returns 401.`
    );
  }

  if (!hasGatewayRoutePrefix(url.pathname)) {
    throw new Error(
      `${name}=${value} is missing a Gateway route prefix ` +
        `(one of ${GATEWAY_ROUTE_PREFIXES.join(", ")}).`
    );
  }
}
