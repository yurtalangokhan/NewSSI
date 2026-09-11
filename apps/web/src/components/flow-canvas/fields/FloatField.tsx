"use client";

import InputNumber from "@/refresh-components/inputs/InputNumber";
import type { FieldRendererProps } from "./types";

/**
 * `InputNumber`'s manual-typing path only accepts whole digits
 * (`/^\d+$/` in its `handleInputChange`) — a pre-existing limitation of
 * the shared component, not something this task fixes (shared surface,
 * out of scope). Fractional values remain reachable via the
 * increment/decrement stepper buttons, which apply `step` directly
 * without that regex. Disclosed in task-26-report.md.
 */
export function FloatField({
  value,
  onChange,
  disabled,
  field,
}: FieldRendererProps) {
  return (
    <InputNumber
      value={typeof value === "number" ? value : field.min ?? 0}
      onChange={onChange}
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      step={0.1}
      disabled={disabled}
    />
  );
}
