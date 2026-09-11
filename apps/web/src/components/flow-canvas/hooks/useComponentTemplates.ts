/**
 * Fetches the component registry (P1 Task 6's GET /flow-components),
 * already grouped by category server-side. Uses `useSWR` per STANDARDS
 * §12 — loaded inside the component that needs it (the sidebar, Task 25;
 * the node renderer, Task 26 reads the same cache key so there is no
 * second fetch), not lifted to a page and passed down.
 *
 * The Next.js proxy route for this (`/api/flow-components`) does not exist
 * yet — that is Task 28's job (it owns all proxy wiring for this phase).
 * This hook points at the eventual real path so no rewiring is needed once
 * Task 28 lands; until then it 404s in a real browser, which is why this
 * task's own tests mock the fetcher rather than hitting a network call.
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import useSWR from "swr";
import { useTranslation } from "react-i18next";
import { languageKeyedFetcher } from "@/lib/fetcher";
import { flowApi } from "@/components/flow-canvas/api/flowApi";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const FLOW_COMPONENTS_URL = flowApi.components();

export function useComponentTemplates() {
  const { i18n } = useTranslation();
  return useSWR<GroupedComponentTemplates>(
    [FLOW_COMPONENTS_URL, i18n.language || "en"],
    languageKeyedFetcher
  );
}
