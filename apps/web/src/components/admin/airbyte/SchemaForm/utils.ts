import { JSONSchemaProperty } from "./types";

/**
 * Resolve a $ref pointer against the schema's definitions.
 * Only supports local #/definitions/<name> references.
 */
export function resolveRef(
  ref: string,
  rootSchema: JSONSchemaProperty
): JSONSchemaProperty {
  if (!ref.startsWith("#/definitions/")) return {};
  const defName = ref.replace("#/definitions/", "");
  return rootSchema.definitions?.[defName] ?? {};
}

/**
 * Resolve a schema node, following $ref if present.
 */
export function resolveSchema(
  schema: JSONSchemaProperty,
  rootSchema: JSONSchemaProperty
): JSONSchemaProperty {
  if (schema.$ref) {
    return resolveRef(schema.$ref, rootSchema);
  }
  return schema;
}

/**
 * Merge allOf schemas into a single flat schema object.
 */
export function mergeAllOf(
  schemas: JSONSchemaProperty[],
  rootSchema: JSONSchemaProperty
): JSONSchemaProperty {
  return schemas.reduce<JSONSchemaProperty>((acc, s) => {
    const resolved = resolveSchema(s, rootSchema);
    return {
      ...acc,
      ...resolved,
      properties: { ...(acc.properties ?? {}), ...(resolved.properties ?? {}) },
      required: [...(acc.required ?? []), ...(resolved.required ?? [])],
    };
  }, {});
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Build the actual connector config represented by a schema and its displayed
 * discriminator branch. Existing values always win, including false and zero.
 */
export function materializeSchemaDefaults(
  rawSchema: JSONSchemaProperty,
  value: unknown,
  rootSchema: JSONSchemaProperty = rawSchema
): unknown {
  let schema = resolveSchema(rawSchema, rootSchema);
  if (schema.allOf) {
    const merged = mergeAllOf(schema.allOf, rootSchema);
    schema = {
      ...schema,
      ...merged,
      properties: {
        ...(schema.properties ?? {}),
        ...(merged.properties ?? {}),
      },
    };
  }

  const variants = schema.oneOf ?? schema.anyOf;
  if (variants?.length) {
    const resolvedVariants = variants.map((variant) => {
      const resolved = resolveSchema(variant, rootSchema);
      return resolved.allOf
        ? { ...resolved, ...mergeAllOf(resolved.allOf, rootSchema) }
        : resolved;
    });
    const discriminatorKey = detectDiscriminatorKey(resolvedVariants);
    if (!discriminatorKey) {
      return materializeSchemaDefaults(
        resolvedVariants[0] ?? {},
        value === undefined ? schema.default : value,
        rootSchema
      );
    }
    const currentObject = isRecord(value) ? value : {};
    const discriminatorValue =
      currentObject[discriminatorKey] ??
      (isRecord(schema.default)
        ? schema.default[discriminatorKey]
        : schema.default);
    const matchedVariant = resolvedVariants.find(
      (variant) =>
        getDiscriminatorValue(variant, discriminatorKey) ===
        String(discriminatorValue)
    );
    if (
      currentObject[discriminatorKey] !== undefined &&
      matchedVariant === undefined
    ) {
      return currentObject;
    }
    const selected = matchedVariant ?? resolvedVariants[0];
    const selectedValue =
      discriminatorValue !== undefined
        ? { ...currentObject, [discriminatorKey]: discriminatorValue }
        : currentObject;
    return materializeSchemaDefaults(selected ?? {}, selectedValue, rootSchema);
  }

  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  if (type === "object" || schema.properties) {
    const defaultObject = isRecord(schema.default) ? schema.default : undefined;
    const currentObject = isRecord(value) ? value : undefined;
    const source = { ...(defaultObject ?? {}), ...(currentObject ?? {}) };
    const result: Record<string, unknown> = { ...source };
    let hasValue = defaultObject !== undefined || currentObject !== undefined;
    for (const [key, propertySchema] of Object.entries(
      schema.properties ?? {}
    )) {
      const next = materializeSchemaDefaults(
        propertySchema,
        source[key],
        rootSchema
      );
      if (next !== undefined) {
        result[key] = next;
        hasValue = true;
      }
    }
    return hasValue ? result : undefined;
  }

  if (value !== undefined) return value;
  if (schema.const !== undefined) return schema.const;
  if (schema.default !== undefined) return schema.default;
  return undefined;
}

/**
 * Sort property entries by the Airbyte `order` field (ascending, undefined last).
 */
export function sortPropertiesByOrder(
  properties: Record<string, JSONSchemaProperty>
): [string, JSONSchemaProperty][] {
  return Object.entries(properties).sort(([, a], [, b]) => {
    const oa = typeof a.order === "number" ? a.order : Infinity;
    const ob = typeof b.order === "number" ? b.order : Infinity;
    return oa - ob;
  });
}

/**
 * Detect whether a oneOf/anyOf array uses a discriminator constant.
 * Returns the property key used as the discriminator, or null.
 *
 * Airbyte pattern: each oneOf entry has a "properties.{key}.const" or
 * "properties.{key}.enum" with a single value to distinguish variants.
 */
export function detectDiscriminatorKey(
  variants: JSONSchemaProperty[]
): string | null {
  if (!variants.length) return null;

  const first = variants[0];
  if (!first?.properties) return null;

  for (const key of Object.keys(first.properties)) {
    const prop = first.properties[key];
    const hasConst = prop?.const !== undefined;
    const hasSingleEnum = Array.isArray(prop?.enum) && prop.enum!.length === 1;

    if (hasConst || hasSingleEnum) {
      // Verify all other variants also have this key as a const/single-enum
      const allMatch = variants.every((v) => {
        const vProp = v.properties?.[key];
        return (
          vProp?.const !== undefined ||
          (Array.isArray(vProp?.enum) && vProp.enum!.length === 1)
        );
      });
      if (allMatch) return key;
    }
  }
  return null;
}

/**
 * Get the discriminator value from a variant for display.
 */
export function getDiscriminatorValue(
  variant: JSONSchemaProperty,
  key: string
): string {
  const prop = variant.properties?.[key];
  if (prop?.const !== undefined) return String(prop.const);
  if (Array.isArray(prop?.enum) && prop.enum!.length === 1)
    return String(prop.enum![0]);
  return variant.title ?? "Option";
}

/**
 * Determine whether a schema represents a primitive type
 * (string, number, integer, boolean) as opposed to object or array.
 */
export function isPrimitive(schema: JSONSchemaProperty): boolean {
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  return ["string", "number", "integer", "boolean"].includes(type ?? "");
}

/**
 * Set a nested value in an object by dot-separated path.
 * Returns a new object (immutable update).
 */
export function setNestedValue(
  obj: Record<string, unknown>,
  path: string[],
  value: unknown
): Record<string, unknown> {
  if (path.length === 0) return obj;
  const [head, ...rest] = path;
  if (rest.length === 0) {
    return { ...obj, [head!]: value };
  }
  return {
    ...obj,
    [head!]: setNestedValue(
      (obj[head!] as Record<string, unknown>) ?? {},
      rest,
      value
    ),
  };
}
