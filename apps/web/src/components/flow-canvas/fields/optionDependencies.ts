/**
 * Carries a field's `depends_on` siblings to the options endpoint.
 *
 * Mirrors the backend contract: `InputField.depends_on` names sibling fields,
 * their values ride as repeated `dep=name:value` query parameters, and the
 * resolver narrows the list server-side (and keys its cache on them).
 *
 * This replaces a client-side special case that split `llm.models`' display
 * `description` on "|" and matched by substring in both directions — so
 * "openai" also matched "openai-compatible", and an empty result silently
 * fell back to every provider's models.
 */

import { flowApi } from "../api/flowApi";
import type { InputField } from "../types/componentTemplate";

/** The values of the siblings `field` declares, skipping the unset ones. */
export function dependencyValues(
  field: InputField,
  allValues: Record<string, unknown> | undefined
): Record<string, string> {
  const names = field.depends_on;
  if (!names || names.length === 0) return {};

  const out: Record<string, string> = {};
  for (const name of names) {
    const raw = allValues?.[name];
    if (raw === undefined || raw === null || raw === "") continue;
    out[name] = String(raw);
  }
  return out;
}

/**
 * The request URL, which is also the SWR cache key — so changing a
 * depended-on value refetches instead of serving the previous provider's list.
 * Keys are sorted so the same dependency set always produces the same string.
 */
export function optionsRequestKey(
  source: string,
  depends: Record<string, string>
): string {
  const names = Object.keys(depends).sort();
  const base = flowApi.componentOptions(source);
  if (names.length === 0) return base;
  const query = names
    .map((name) => `dep=${encodeURIComponent(`${name}:${depends[name]}`)}`)
    .join("&");
  return `${base}?${query}`;
}
