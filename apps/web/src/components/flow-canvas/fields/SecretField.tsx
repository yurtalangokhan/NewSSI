"use client";

import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import type { FieldRendererProps } from "./types";

export function SecretField({ value, onChange, disabled }: FieldRendererProps) {
  return (
    <PasswordInputTypeIn
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
    />
  );
}
