/**
 * The one proxy route P1/P4 needed that didn't already exist — mirrors
 * `src/app/api/agent-definitions/[...path]/route.ts`'s shape exactly.
 * Covers all three of `FlowComponentsRoute.py`'s GET endpoints from a
 * single optional catch-all (`[[...path]]`, not `[...path]`, so the base
 * `/api/flow-components` path itself — no segments — also matches):
 *
 *   GET /flow-components                 (base, no path segments)
 *   GET /flow-components/options/{source}
 *   GET /flow-components/{type}
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

function flowComponentsPath(path: string[] | undefined) {
  const suffix = (path ?? []).join("/");
  return `/flow-components${suffix ? `/${suffix}` : ""}`;
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path?: string[] }> }
) {
  return proxyToBackend(request, flowComponentsPath((await props.params).path));
}
