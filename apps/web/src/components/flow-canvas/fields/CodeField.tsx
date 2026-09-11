"use client";

import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import { cn } from "@/lib/utils";
import type { FieldRendererProps } from "./types";

/**
 * `refresh-components/Code.tsx` was confirmed read-only during this task
 * (a `children: string` viewer with a copy button, no `onChange` at all)
 * — not assumed. Per the brief's own allowance, this is the one place a
 * light editor is justified: a monospace `InputTextArea`, not a full
 * code editor (no such dependency — CodeMirror/Monaco — exists in this
 * project, and adding one is out of scope for a single field type).
 */
export function CodeField({ value, onChange, disabled }: FieldRendererProps) {
  return (
    <InputTextArea
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      variant={disabled ? "disabled" : undefined}
      className={cn("font-mono")}
      autoResize
      maxRows={20}
    />
  );
}
