const PUBLIC_SURFACE_PREFIXES = ["/auth", "/error"];

export function shouldRenderAppShell(pathname: string | null | undefined) {
  if (!pathname || pathname === "/") {
    return false;
  }

  return !PUBLIC_SURFACE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
