/**
 * `FieldType` -> renderer registry. `fields.test.tsx`'s 26.1 asserts this
 * has no silent gap against `ALL_FIELD_TYPES` (types/componentTemplate.ts)
 * — the single source of truth for the 13 values.
 */

import type { ComponentType } from "react";
import type { FieldType } from "../types/componentTemplate";
import type { FieldRendererProps } from "./types";
import { StrField } from "./StrField";
import { IntField } from "./IntField";
import { FloatField } from "./FloatField";
import { BoolField } from "./BoolField";
import { SliderField } from "./SliderField";
import { OptionsField } from "./OptionsField";
import { MultiselectField } from "./MultiselectField";
import { SecretField } from "./SecretField";
import { PromptField } from "./PromptField";
import { CodeField } from "./CodeField";
import { TableField } from "./TableField";
import { FileField } from "./FileField";
import { JsonField } from "./JsonField";

export const FIELD_RENDERERS: Record<
  FieldType,
  ComponentType<FieldRendererProps>
> = {
  str: StrField,
  int: IntField,
  float: FloatField,
  bool: BoolField,
  slider: SliderField,
  options: OptionsField,
  multiselect: MultiselectField,
  secret: SecretField,
  prompt: PromptField,
  code: CodeField,
  table: TableField,
  file: FileField,
  json: JsonField,
};

export type { FieldRendererProps } from "./types";
