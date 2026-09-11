"use client";

import InputNumber from "@/refresh-components/inputs/InputNumber";
import type { FieldRendererProps } from "./types";

export function IntField({
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
      step={1}
      disabled={disabled}
    />
  );
}
