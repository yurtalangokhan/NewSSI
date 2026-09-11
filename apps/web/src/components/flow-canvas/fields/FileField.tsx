"use client";

import InputFile from "@/refresh-components/inputs/InputFile";
import type { FieldRendererProps } from "./types";

/**
 * Known gap: `InputFile` manages its displayed filename/text internally
 * and has no prop to seed it from an existing `value` — reopening a node
 * whose field already holds previously-uploaded file content shows an
 * empty picker, not "already attached." The underlying value is not
 * lost (still read from `node.data.values` on save), only the visual
 * "a file is attached" affordance is missing on reload. Disclosed in
 * task-26-report.md; fixing it means changing the shared `InputFile`
 * component's API (out of scope for this task).
 */
export function FileField({ onChange, disabled }: FieldRendererProps) {
  return (
    <InputFile
      setValue={onChange}
      variant={disabled ? "disabled" : undefined}
    />
  );
}
