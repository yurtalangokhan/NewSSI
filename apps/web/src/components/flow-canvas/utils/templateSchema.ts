/**
 * Mirrors apps/agent-service/src/domain/flows/handles.py exactly.
 *
 * Two questions the canvas and the validator must answer identically: which
 * output handles a node really has, and whether a field is visible. Both are
 * declared on the template, so a new component that needs either costs no
 * code here — this file has no per-component-type branch, deliberately. The
 * `Router: {...}` special cases it replaced are exactly how the backend and
 * the canvas drifted apart before.
 */

import type {
  ComponentTemplate,
  Handle,
  InputField,
  ShowWhen,
} from "../types/componentTemplate";

function ruleHolds(
  rule: ShowWhen | null | undefined,
  resolved: Record<string, unknown>
): boolean {
  if (!rule) return true;
  const actual = resolved[rule.field];
  if (
    rule.equals !== undefined &&
    rule.equals !== null &&
    actual !== rule.equals
  )
    return false;
  if (
    rule.not_equals !== undefined &&
    rule.not_equals !== null &&
    actual === rule.not_equals
  )
    return false;
  if (rule.one_of && !rule.one_of.includes(actual)) return false;
  if (rule.not_one_of && rule.not_one_of.includes(actual)) return false;
  return true;
}

export function resolvedValues(
  template: ComponentTemplate,
  values: Record<string, unknown>
): Record<string, unknown> {
  const merged: Record<string, unknown> = {};
  for (const [name, field] of Object.entries(template.inputs))
    merged[name] = field.value;
  return { ...merged, ...(values ?? {}) };
}

function rowLabel(row: unknown, labelKey: string): string | null {
  if (typeof row === "string") return row;
  if (row && typeof row === "object") {
    const value = (row as Record<string, unknown>)[labelKey];
    if (typeof value === "string") return value;
  }
  return null;
}

export function getEffectiveOutputHandles(
  template: ComponentTemplate,
  values: Record<string, unknown>
): Handle[] {
  const resolved = resolvedValues(template, values);
  const result: Handle[] = [];
  for (const handle of template.handles.outputs) {
    if (!ruleHolds(handle.show_when, resolved)) continue; // conditional port switched off
    const from = handle.expands_from;
    const labelKey = handle.expands_label_key;
    if (!from || !labelKey) {
      result.push({ name: handle.name, types: handle.types });
      continue;
    }
    const rows = resolved[from];
    const labels = Array.isArray(rows)
      ? rows
          .map((r) => rowLabel(r, labelKey))
          .filter((l): l is string => !!l && l.trim() !== "")
      : [];
    if (labels.length === 0) {
      result.push({ name: handle.name, types: handle.types });
      continue;
    }
    for (const label of labels)
      result.push({ name: label, types: handle.types });
  }
  return result;
}

/**
 * The mirror of the backend's `effective_input_handles`. No component expands
 * an input from a table today, so this only applies `show_when` — but every
 * caller goes through it rather than reading `template.handles.inputs`
 * directly, so a port that becomes conditional cannot drift the two sides
 * apart.
 */
export function getEffectiveInputHandles(
  template: ComponentTemplate,
  values: Record<string, unknown>
): Handle[] {
  const resolved = resolvedValues(template, values);
  return template.handles.inputs.filter((h) =>
    ruleHolds(h.show_when, resolved)
  );
}

export function fieldVisible(
  field: InputField,
  resolved: Record<string, unknown>
): boolean {
  return ruleHolds(field.show_when, resolved);
}

export function visibleInputs(
  template: ComponentTemplate,
  values: Record<string, unknown>
): Record<string, InputField> {
  const resolved = resolvedValues(template, values);
  const out: Record<string, InputField> = {};
  for (const [name, field] of Object.entries(template.inputs)) {
    if (fieldVisible(field, resolved)) out[name] = field;
  }
  return out;
}
