/**
 * Utility functions for the recursive JSON Schema form renderer.
 */

import type { JSONSchema7, OneOfOption } from "./types";

// ---------------------------------------------------------------------------
// Default values
// ---------------------------------------------------------------------------

export function getDefaultValue(schema: JSONSchema7): any {
  if (schema.default !== undefined) return schema.default;
  if (schema.const !== undefined) return schema.const;

  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  switch (type) {
    case "string":
      return "";
    case "number":
    case "integer":
      return undefined;
    case "boolean":
      return false;
    case "array":
      return [];
    case "object":
      return {};
    default:
      return undefined;
  }
}

// ---------------------------------------------------------------------------
// oneOf / anyOf helpers
// ---------------------------------------------------------------------------

/**
 * Extract discriminator info from a oneOf branch.
 * A discriminator is a property whose schema has a `const` value.
 */
function findDiscriminator(
  schema: JSONSchema7,
): { key: string; value: any } | undefined {
  if (!schema.properties) return undefined;
  for (const [key, propSchema] of Object.entries(schema.properties)) {
    if (propSchema.const !== undefined) {
      return { key, value: propSchema.const };
    }
    // Airbyte sometimes uses enum with single value as discriminator
    if (propSchema.enum && propSchema.enum.length === 1) {
      return { key, value: propSchema.enum[0] };
    }
  }
  return undefined;
}

/**
 * Build display-friendly OneOfOption list from schema.oneOf / schema.anyOf.
 */
export function buildOneOfOptions(
  branches: JSONSchema7[],
): OneOfOption[] {
  return branches.map((branch, index) => {
    const disc = findDiscriminator(branch);
    const title =
      branch.title ||
      disc?.value?.toString() ||
      `Option ${index + 1}`;

    return { index, title, schema: branch, discriminator: disc };
  });
}

/**
 * Detect which oneOf branch is currently selected based on current values.
 * Matches by discriminator const field value.
 */
export function detectOneOfBranch(
  options: OneOfOption[],
  values: any,
): number {
  if (!values || typeof values !== "object") return 0;

  for (const opt of options) {
    if (opt.discriminator) {
      const { key, value } = opt.discriminator;
      if (values[key] === value) return opt.index;
    }
  }

  return 0; // default to first
}

// ---------------------------------------------------------------------------
// allOf merge
// ---------------------------------------------------------------------------

export function mergeAllOf(schemas: JSONSchema7[]): JSONSchema7 {
  const merged: JSONSchema7 = { type: "object", properties: {}, required: [] };

  for (const s of schemas) {
    if (s.properties) {
      merged.properties = { ...merged.properties, ...s.properties };
    }
    if (s.required) {
      merged.required = [...(merged.required || []), ...s.required];
    }
    if (s.title && !merged.title) merged.title = s.title;
    if (s.description && !merged.description) merged.description = s.description;
  }

  return merged;
}

// ---------------------------------------------------------------------------
// $ref resolution (basic — Airbyte specs rarely use top-level $ref)
// ---------------------------------------------------------------------------

export function resolveRef(
  schema: JSONSchema7,
  rootSchema?: JSONSchema7,
): JSONSchema7 {
  if (!schema.$ref || !rootSchema) return schema;

  const path = schema.$ref.replace("#/", "").split("/");
  let resolved: any = rootSchema;
  for (const segment of path) {
    resolved = resolved?.[segment];
  }
  return (resolved as JSONSchema7) || schema;
}

// ---------------------------------------------------------------------------
// Field ordering
// ---------------------------------------------------------------------------

export function getFieldOrder(schema: JSONSchema7): string[] {
  const props = schema.properties || {};
  const keys = Object.keys(props);

  // Airbyte "order" extension — can be an array of keys or each prop has .order
  if (Array.isArray(schema.order)) {
    const ordered = schema.order.filter((k) =>
      typeof k === "string" && keys.includes(k),
    );
    const rest = keys.filter((k) => !ordered.includes(k));
    return [...ordered, ...rest];
  }

  // Per-property .order number
  const hasOrder = keys.some((k) => typeof props[k].order === "number");
  if (hasOrder) {
    return [...keys].sort((a, b) => {
      const oa = typeof props[a].order === "number" ? (props[a].order as number) : 999;
      const ob = typeof props[b].order === "number" ? (props[b].order as number) : 999;
      return oa - ob;
    });
  }

  // Required fields first, then alphabetical
  const required = new Set(schema.required || []);
  const reqKeys = keys.filter((k) => required.has(k));
  const optKeys = keys.filter((k) => !required.has(k));
  return [...reqKeys, ...optKeys];
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

export function isRequired(key: string, parentSchema: JSONSchema7): boolean {
  return parentSchema.required?.includes(key) ?? false;
}

export function isHidden(schema: JSONSchema7): boolean {
  return schema.airbyte_hidden === true;
}

export function isSecret(schema: JSONSchema7, key?: string): boolean {
  if (schema.airbyte_secret) return true;
  if (!key) return false;
  const lower = key.toLowerCase();
  return (
    lower.includes("password") ||
    lower.includes("secret") ||
    lower.includes("api_key") ||
    lower.includes("access_token")
  );
}
