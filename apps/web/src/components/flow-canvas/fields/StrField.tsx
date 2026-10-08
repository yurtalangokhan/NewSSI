"use client";

import { useTranslation } from "react-i18next";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { resolveFieldName } from "./fieldName";
import type { FieldRendererProps } from "./types";

export function StrField({
  fieldKey,
  field,
  value,
  onChange,
  disabled,
  componentType,
}: FieldRendererProps) {
  const { t } = useTranslation();
  return (
    <InputTypeIn
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      variant={disabled ? "disabled" : undefined}
      /* The field's own name, in the active locale — not the server's raw
         English `display_name`, which is only the fallback. */
      placeholder={resolveFieldName(t, fieldKey, field, componentType)}
    />
  );
}
