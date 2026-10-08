import { User } from "@/lib/types";
import {
  getAuthTypeMetadataSS,
  getCurrentUserSS,
  getCurrentUserAccessSS,
} from "@/lib/api/domains/session/server";
import type { AuthTypeMetadata } from "@/lib/api/domains/session/types";
import { getLoginPath } from "@/lib/auth/loginRoute";
import {
  canAccessAdminPanel,
  getAdminRouteConfigForPathname,
} from "@/lib/navigation/admin-routes";
import { hasAllPermissions } from "@/lib/auth/permissions";

/**
 * Result of an authentication check.
 * If redirect is set, the caller should redirect immediately.
 */
export interface AuthCheckResult {
  user: User | null;
  authTypeMetadata: AuthTypeMetadata | null;
  redirect?: string;
}

/**
 * Requires that the user is authenticated.
 * If not authenticated and auth is enabled, returns a redirect to login.
 * Also checks email verification if required.
 *
 * @returns AuthCheckResult with user, auth metadata, and optional redirect
 *
 * @example
 * ```typescript
 * const authResult = await requireAuth();
 * if (authResult.redirect) {
 *   return redirect(authResult.redirect);
 * }
 * // User is authenticated, proceed with logic
 * const { user } = authResult;
 * ```
 */
export async function requireAuth(): Promise<AuthCheckResult> {
  // Fetch auth information
  let user: User | null = null;
  let authTypeMetadata: AuthTypeMetadata | null = null;

  try {
    [authTypeMetadata, user] = await Promise.all([
      getAuthTypeMetadataSS(),
      getCurrentUserSS(),
    ]);
  } catch (e) {
    console.log(`Failed to fetch auth information - ${e}`);
  }

  if (!user) {
    return {
      user: null,
      authTypeMetadata,
      redirect: getLoginPath(authTypeMetadata),
    };
  }

  // Check email verification if required
  if (user && !user.is_verified && authTypeMetadata?.requiresVerification) {
    return {
      user,
      authTypeMetadata,
      redirect: "/auth/waiting-on-verification",
    };
  }

  return {
    user,
    authTypeMetadata,
  };
}

/**
 * Requires authentication and admin-area permissions. When pathname is given,
 * requires the matching page's view permission before server rendering.
 * If not authenticated, redirects to login.
 * If authenticated but unauthorized, redirects to /error/403.
 * Also checks email verification if required.
 *
 * @returns AuthCheckResult with user, auth metadata, and optional redirect
 *
 * @example
 * ```typescript
 * const authResult = await requireAdminAuth();
 * if (authResult.redirect) {
 *   return redirect(authResult.redirect);
 * }
 * // User is authenticated and authorized, proceed with admin logic
 * const { user } = authResult;
 * ```
 */
export async function requireAdminAuth(
  pathname?: string
): Promise<AuthCheckResult> {
  const authResult = await requireAuth();

  // If already has a redirect (not authenticated or not verified), return it
  if (authResult.redirect) {
    return authResult;
  }

  const { user, authTypeMetadata } = authResult;

  // The route registry is the source of truth for admin-area access. Without
  // a pathname, at least one enabled page is enough to enter the admin panel.
  const { permissions } = await getCurrentUserAccessSS();
  const route = pathname ? getAdminRouteConfigForPathname(pathname) : null;
  const authorized = pathname
    ? Boolean(
        route &&
          route.enabled !== false &&
          route.requiredPermissions.length > 0 &&
          hasAllPermissions(permissions, route.requiredPermissions)
      )
    : canAccessAdminPanel(permissions);
  if (!authorized) {
    return {
      user,
      authTypeMetadata,
      redirect: "/error/403",
    };
  }

  return authResult;
}
