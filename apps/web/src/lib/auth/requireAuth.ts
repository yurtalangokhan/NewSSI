import { User } from "@/lib/types";
import {
  AuthTypeMetadata,
  getAuthTypeMetadataSS,
  getCurrentUserSS,
} from "@/lib/userSS";
import { getLoginPath } from "@/lib/auth/loginRoute";

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
 * Requires that the user is authenticated.
 * If not authenticated, redirects to login.
 *
 * Fine-grained admin route authorization is handled by ClientLayout after it
 * loads effective permissions from user-service.
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
 * // User is authenticated, proceed with permission-based admin checks
 * const { user } = authResult;
 * ```
 */
export async function requireAdminAuth(): Promise<AuthCheckResult> {
  return requireAuth();
}
