/**
 * Handle colours, taken **verbatim** from Langflow's own palette
 * (vendor/langflow/utils/styleUtils.ts → `nodeColors`). These are literal
 * hex values rather than theme tokens on purpose: in Langflow they are
 * fixed brand colours that identify a port's data type at a glance, and
 * they read identically in light and dark themes. Re-deriving them from
 * our palette would change the design, which is exactly what we're not
 * doing here.
 *
 * `Trigger` has no Langflow counterpart — it is our own port type (a pure
 * control-flow signal with no payload, design spec §4.7). It takes
 * Langflow's `chains` orange, the colour that family already uses for
 * control flow, rather than an invented one.
 */

import type { PortType } from "../types/flow";

export const PORT_COLORS: Record<PortType, string> = {
  // vendor/langflow/utils/styleUtils.ts:159  "Message": "#4f46e5"
  Message: "#4f46e5",
  // :156  "str"/"Text": "#4F46E5"
  Text: "#4F46E5",
  // :155  "Document": "#65a30d"
  Documents: "#65a30d",
  // :165  "Tool": "#00fbfc"
  Tools: "#00fbfc",
  // :163  "LanguageModel": "#c026d3"
  Model: "#c026d3",
  // :129  "memories": "#F5B85A"
  Memory: "#F5B85A",
  // :164  "Agent": "#903BBE"
  Agent: "#903BBE",
  // :157  "Data": "#dc2626"
  Data: "#dc2626",
  // :125  "chains": "#FE7500" — our port type, Langflow's control-flow colour
  Trigger: "#FE7500",
};

/** Langflow paints a handle by its *first* declared type. */
export function portColor(types: readonly string[]): string {
  const first = types[0] as PortType | undefined;
  return (first && PORT_COLORS[first]) || "#9CA3AF"; // styleUtils.ts:154 "unknown"
}
