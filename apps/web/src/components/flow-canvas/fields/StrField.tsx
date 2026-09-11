"use client";

import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import type { FieldRendererProps } from "./types";

export function StrField({
  value,
  onChange,
  disabled,
  field,
}: FieldRendererProps) {
  return (
    <InputTypeIn
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      variant={disabled ? "disabled" : undefined}
      placeholder={field.display_name}
    />
  );
}
