/**
 * The visible name of an input field, resolved once for every surface that
 * shows it.
 *
 * Field copy lives under `flowCanvas.fields.names`, optionally scoped by
 * component (`LLMModel.model` overriding the generic `model`). `NodeFieldList`
 * (the label), the field renderers (text placeholder, slider aria-label,
 * expanded prompt modal title) and the node's handle rows all read the same
 * chain here, so one field never renders under two different names — and a
 * missing locale key falls back to the template's own `display_name`.
 */

import type { TFunction } from "i18next";
import type { InputField } from "../types/componentTemplate";

export function resolveFieldName(
  t: TFunction,
  fieldKey: string,
  field: InputField,
  componentType?: string
): string {
  return componentType
    ? t(
        [
          `flowCanvas.fields.names.${componentType}.${fieldKey}`,
          `flowCanvas.fields.names.${fieldKey}`,
        ],
        field.display_name
      )
    : t(`flowCanvas.fields.names.${fieldKey}`, field.display_name);
}
