"use client";

import { useTheme } from "next-themes";
import useOnMount from "@/hooks/useOnMount";

export type ResolvedColorMode = "light" | "dark";

/**
 * The color mode actually in effect ("system" already resolved), safe to use
 * in server-rendered markup: `next-themes` reads the stored theme
 * synchronously on the client, so consuming `resolvedTheme` directly on the
 * first render would not match the server's output. Until mount this returns
 * "light" — the same value the server rendered.
 */
export default function useResolvedColorMode(): ResolvedColorMode {
  const { resolvedTheme } = useTheme();
  const mounted = useOnMount();
  return mounted && resolvedTheme === "dark" ? "dark" : "light";
}
