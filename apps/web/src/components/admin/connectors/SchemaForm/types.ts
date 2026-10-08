/**
 * JSON Schema types for connector configuration forms, with the extensions the
 * connector catalog emits on top of standard JSON Schema:
 *   - x-secret / writeOnly: marks a field as a password/secret
 *   - x-hidden: hides a field from the UI
 *   - x-json: a text area whose content is JSON (mappings, lists of objects)
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

  // Connector catalog extensions
  "x-secret"?: boolean;
  writeOnly?: boolean;
  "x-hidden"?: boolean;
  "x-json"?: boolean;
  order?: number | number[];
}

export interface ResolvedSchemaProperty extends JSONSchemaProperty {
  /** Key name of this property within its parent object */
  _key?: string;
}
