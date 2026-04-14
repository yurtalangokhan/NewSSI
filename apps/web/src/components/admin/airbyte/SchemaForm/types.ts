/**
 * JSON Schema Draft-7 types with Airbyte-specific extensions.
 * Airbyte extends standard JSON Schema with:
 *   - airbyte_secret: marks a field as a password/secret
 *   - airbyte_hidden: hides a field from the UI
 *   - order: controls field display order (number or array for per-property)
 */

export interface JSONSchemaProperty {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  examples?: unknown[];
  enum?: unknown[];
  const?: unknown;

  // String constraints
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  format?: string;

  // Number constraints
  minimum?: number;
  maximum?: number;
  multipleOf?: number;

  // Object properties
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
  additionalProperties?: boolean | JSONSchemaProperty;

  // Array items
  items?: JSONSchemaProperty | JSONSchemaProperty[];
  minItems?: number;
  maxItems?: number;

  // Composition
  oneOf?: JSONSchemaProperty[];
  anyOf?: JSONSchemaProperty[];
  allOf?: JSONSchemaProperty[];
  $ref?: string;
  $schema?: string;
  definitions?: Record<string, JSONSchemaProperty>;

  // Airbyte extensions
  airbyte_secret?: boolean;
  airbyte_hidden?: boolean;
  order?: number | number[];
}

export interface ResolvedSchemaProperty extends JSONSchemaProperty {
  /** Key name of this property within its parent object */
  _key?: string;
}
