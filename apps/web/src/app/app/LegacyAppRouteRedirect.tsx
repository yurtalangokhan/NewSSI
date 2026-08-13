"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { buildCanonicalAppPathFromSearch } from "@/hooks/appNavigation";

export default function LegacyAppRouteRedirect() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (pathname !== "/app") {
      return;
    }

    const canonicalPath = buildCanonicalAppPathFromSearch(searchParams);
    if (canonicalPath) {
      router.replace(canonicalPath as Route, { scroll: false });
    }
  }, [pathname, router, searchParams]);

  return null;
}
