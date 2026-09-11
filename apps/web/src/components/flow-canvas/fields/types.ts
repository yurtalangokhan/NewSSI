import type { InputField, TableColumn } from "../types/componentTemplate";

export type FieldRendererProps = {
  fieldKey: string;
  field: InputField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  /** TABLE only — the field's column metadata, so each cell renders as its
   * declared type. Passed through by NodeFieldList from `field.columns`. */
  columns?: TableColumn[];
  /** Sibling field values on the same node (e.g. provider selection for model filtering). */
  allValues?: Record<string, unknown>;
};
