/**
 * Search matching for the component sidebar.
 *
 * Concept ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/flowSidebarComponent/helpers/normalize-string.ts
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx: Langflow's matcher is Fuse.js-backed and spread across
 * ~8 helper files (apply-beta-filter, apply-legacy-filter, apply-edge-filter,
 * combined-results, …) that encode concepts we don't have — component
 * "bundles", a separate legacy-component toggle, edge-vs-node filtering.
 * Rather than add a new dependency (Fuse.js) to port machinery mostly
 * built for filters this registry doesn't have, this is a from-scratch,
 * dependency-free reimplementation of the *behavior* the brief actually
 * asked for: tolerate partial terms and terms typed in any order. See
 * task-25-report.md for the full reasoning.
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import i18n from "i18next";
import type { ComponentTemplate } from "../types/componentTemplate";

function normalize(value: string): string {
  return value.toLowerCase().replace(/[-_]/g, " ").replace(/\s+/g, " ").trim();
}

export function matchesSearch(
  query: string,
  template: ComponentTemplate
): boolean {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return true;

  const translatedName = i18n.t(
    `flowCanvas.components.${template.type}.name`,
    template.display_name
  );
  const translatedDesc = i18n.t(
    `flowCanvas.components.${template.type}.description`,
    template.description || ""
  );

  const haystack = normalize(
    `${template.display_name} ${
      template.description || ""
    } ${translatedName} ${translatedDesc}`
  );
  const queryTokens = normalizedQuery.split(" ").filter(Boolean);

  // Every query token must appear somewhere in the haystack — order-
  // independent, so "input chat" matches "Chat Input" just as "chat input" does.
  return queryTokens.every((token) => haystack.includes(token));
}

export function filterGroupedTemplates(
  grouped: Record<string, ComponentTemplate[]>,
  query: string
): Record<string, ComponentTemplate[]> {
  if (!query.trim()) return grouped;

  const filtered: Record<string, ComponentTemplate[]> = {};
  for (const [category, templates] of Object.entries(grouped)) {
    const matches = templates.filter((t) => matchesSearch(query, t));
    if (matches.length > 0) filtered[category] = matches;
  }
  return filtered;
}
