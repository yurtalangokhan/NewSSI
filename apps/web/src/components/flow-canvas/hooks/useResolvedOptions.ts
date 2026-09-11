/**
 * Resolves a dynamic `options_source` (P1 Task 5, 12 sources) via
 * `GET /flow-components/options/{source}`. Mirrors
 * apps/agent-service/src/api/routes/FlowComponentsRoute.py's response
 * shape exactly: `{ source, available, items }`, `items` built from the
 * backend's `OptionItem` dataclass (`domain/flows/resolvers.py`).
 *
 * `available: false` carries no reason string from the backend today —
 * `ResolvedOptions` only has `source`/`items`/`available`. OptionsField and
 * MultiselectField can only show a generic explanation, not a dynamic one
 * (see task-26-report.md).
 *
 * Brief: .tmp/flow-canvas-task-26-brief.md
 */

import useSWR from "swr";
import { useTranslation } from "react-i18next";
import { languageKeyedFetcher } from "@/lib/fetcher";
import { optionsRequestKey } from "@/components/flow-canvas/fields/optionDependencies";

export type ResolvedOptionItem = {
  value: string;
  label: string;
  description?: string | null;
  disabled?: boolean;
};

export type ResolvedOptionsResponse = {
  source: string;
  available: boolean;
  items: ResolvedOptionItem[];
};

/**
 * `depends` carries the values of the sibling fields the field declares in
 * `depends_on`. They are part of the request URL and therefore part of the
 * SWR key, so changing the selected provider refetches rather than serving
 * the previous provider's models.
 */
export function useResolvedOptions(
  source: string | null,
  depends: Record<string, string> = {}
) {
  const { i18n } = useTranslation();
  return useSWR<ResolvedOptionsResponse>(
    source ? [optionsRequestKey(source, depends), i18n.language || "en"] : null,
    languageKeyedFetcher
  );
}
