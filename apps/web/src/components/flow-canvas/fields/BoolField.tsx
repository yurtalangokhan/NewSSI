"use client";

import Switch from "@/refresh-components/inputs/Switch";
import type { FieldRendererProps } from "./types";

export function BoolField({ value, onChange, disabled }: FieldRendererProps) {
  return (
    <Switch
      checked={typeof value === "boolean" ? value : false}
      onCheckedChange={onChange}
      disabled={disabled}
    />
  );
}
