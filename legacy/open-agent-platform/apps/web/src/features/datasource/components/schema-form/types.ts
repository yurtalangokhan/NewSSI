/**
 * Types for the recursive JSON Schema form renderer.
 *
 * Supports standard JSON Schema Draft-7 with Airbyte extensions
 * (airbyte_secret, airbyte_hidden, order).
 */

// ---------------------------------------------------------------------------
// JSON Schema (Draft-7 subset used by Airbyte specs)
// ---------------------------------------------------------------------------

export interface JSONSchema7 {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: any;
  const?: any;
  enum?: any[];
  format?: string;
  examples?: any[];

  // Object
  properties?: Record<string, JSONSchema7>;
  required?: string[];
  additionalProperties?: boolean | JSONSchema7;

  // Composition
  oneOf?: JSONSchema7[];
  anyOf?: JSONSchema7[];
  allOf?: JSONSchema7[];
  $ref?: string;

  // Array
  items?: JSONSchema7;
  minItems?: number;
  maxItems?: number;

  // Number
  minimum?: number;
  maximum?: number;
  multipleOf?: number;

  // String
  minLength?: number;
  maxLength?: number;
  pattern?: string;

  // Conditional
  if?: JSONSchema7;
  then?: JSONSchema7;
  else?: JSONSchema7;

  // Airbyte extensions
  airbyte_secret?: boolean;
  airbyte_hidden?: boolean;
  order?: number | string[];

  // Catch-all for unknown vendor extensions
  [key: string]: any;
}

// ---------------------------------------------------------------------------
// Component props
// ---------------------------------------------------------------------------

export interface SchemaFormProps {
  /** Raw JSON Schema for the field / section. */
  schema: JSONSchema7;
  /** Current values at this path level. */
  values: any;
  /** Callback when values change. */
  onChange: (values: any) => void;
  /** Property path from root (e.g. ["credentials", "api_key"]). */
  path?: string[];
  /** Whether this field is required by its parent schema. */
  required?: boolean;
  /** The root schema – used for $ref resolution. */
  rootSchema?: JSONSchema7;
}

export interface OneOfOption {
  index: number;
  title: string;
  schema: JSONSchema7;
  discriminator?: { key: string; value: any };
}
