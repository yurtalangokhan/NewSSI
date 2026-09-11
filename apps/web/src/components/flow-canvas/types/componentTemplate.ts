/**
 * Mirrors apps/agent-service/src/models/flows.py's ComponentTemplate exactly
 * — string enum values included (backend serializes "stable"/"execution",
 * lowercase). This is the server-owned registry entry the sidebar (Task 25)
 * and node renderer (Task 26) both read; the canvas never invents or
 * caches its own copy of a template's fields (R1, §4.4).
 */

export type ComponentKind = "execution" | "resource";
export type Lifecycle = "stable" | "beta" | "deprecated";

export type FieldType =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "slider"
  | "options"
  | "multiselect"
  | "secret"
  | "prompt"
  | "code"
  | "table"
  | "file"
  | "json";

export type TableColumn = {
  name: string;
  display_name: string;
  /** Mirrors the backend's `TableColumn.type`; drives how the cell renders. */
  type?: string;
  /** For an `options` column, the values the cell may take. */
  options?: string[] | null;
};

export type ShowWhen = {
  field: string;
  equals?: unknown;
  not_equals?: unknown;
  one_of?: unknown[];
  not_one_of?: unknown[];
};

export type InputField = {
  type: FieldType;
  display_name: string;
  required: boolean;
  value: unknown;
  options: string[] | null;
  options_source: string | null;
  info: string | null;
  advanced: boolean;
  min: number | null;
  max: number | null;
  step?: number | null;
  show_when?: ShowWhen | null;
  columns?: TableColumn[] | null;
  /**
   * Sibling fields this field's `options_source` depends on. Their values are
   * sent to the resolver, which narrows the list server-side. Mirrors the
   * backend's `InputField.depends_on`.
   */
  depends_on?: string[] | null;
};

export type Handle = {
  name: string;
  types: string[]; // PortType values
  expands_from?: string | null;
  expands_label_key?: string | null;
  show_when?: ShowWhen | null;
  /**
   * Input field read when no edge is wired to this port. Mirrors the
   * backend's `Handle.fallback_field`: a wired port always wins, otherwise
   * this field is read. May equal the handle's own name.
   */
  fallback_field?: string | null;
};

export type ComponentHandles = {
  inputs: Handle[];
  outputs: Handle[];
};

export type ComponentTemplate = {
  type: string;
  category: string;
  display_name: string;
  description: string;
  icon: string | null;
  template_version: number;
  lifecycle: Lifecycle;
  kind: ComponentKind;
  inputs: Record<string, InputField>;
  handles: ComponentHandles;
  /**
   * The boolean field that flips this component into an agent tool. Mirrors
   * the backend's `ComponentTemplate.tool_mode_field`; a component without it
   * does not have the capability.
   */
  tool_mode_field?: string | null;
};

/** The shape of GET /flow-components (P1 Task 6) — already grouped
 * server-side, so the sidebar renders categories as given rather than
 * grouping client-side. */
export type GroupedComponentTemplates = Record<string, ComponentTemplate[]>;

/** Single source of truth for "every FieldType has a renderer" (26.1) —
 * both fields/index.ts's registry and its completeness test derive from
 * this instead of each re-listing the 13 values and risking drift. */
export const ALL_FIELD_TYPES: readonly FieldType[] = [
  "str",
  "int",
  "float",
  "bool",
  "slider",
  "options",
  "multiselect",
  "secret",
  "prompt",
  "code",
  "table",
  "file",
  "json",
];
