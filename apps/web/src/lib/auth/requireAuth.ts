import { User } from "@/lib/types";
import {
  AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
  getCurrentUserPermissionsSS,
} from "@/lib/userSS";
import { getLoginPath } from "@/lib/auth/loginRoute";
import { isAdminFromPermissions } from "@/lib/auth/roles";

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
 * Requires that the user is authenticated and has admin-area permissions.
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
export async function requireAdminAuth(): Promise<AuthCheckResult> {
  const authResult = await requireAuth();

  // If already has a redirect (not authenticated or not verified), return it
  if (authResult.redirect) {
    return authResult;
  }

  const { user, authTypeMetadata } = authResult;

  const permissions = await getCurrentUserPermissionsSS();
  if (!isAdminFromPermissions(permissions)) {
    return {
      user,
      authTypeMetadata,
      redirect: "/error/403",
    };
  }

  return authResult;
}
