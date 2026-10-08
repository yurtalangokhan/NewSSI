/** Read caches refreshed together after changes made directly in Keycloak. */
export function isIdentityCatalogKey(key: unknown): boolean {
  return (
    (typeof key === "string" &&
      /^\/api\/user-service\/(?:roles|coarse-roles|permissions)\/?$/.test(
        key
      )) ||
    (typeof key === "string" &&
      /^\/api\/user-service\/(?:roles|coarse-roles)\/[^/]+\/(?:permissions|role-ids)$/.test(
        key
      ))
  );
}
