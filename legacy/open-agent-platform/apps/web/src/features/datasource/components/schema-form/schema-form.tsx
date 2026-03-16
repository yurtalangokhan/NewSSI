"use client";

import type { SchemaFormProps } from "./types";
import { mergeAllOf, resolveRef } from "./utils";
import { OneOfField } from "./one-of-field";
import { ObjectField } from "./object-field";
import { PrimitiveField } from "./primitive-field";
import { ArrayField } from "./array-field";

/**
 * Root recursive entry point for rendering a JSON Schema form.
 *
 * Dispatches to the appropriate sub-component based on schema structure:
 *   - oneOf / anyOf → OneOfField (dropdown selector)
 *   - allOf → merge then re-dispatch
 *   - object → ObjectField (iterate properties)
 *   - array → ArrayField (add/remove items)
 *   - primitive → PrimitiveField (input / select / switch)
 *   - const → hidden (auto-set value)
 */
export function SchemaForm({
  schema: rawSchema,
  values,
  onChange,
  path = [],
  required = false,
  rootSchema,
}: SchemaFormProps) {
  // Resolve $ref if present
  const schema = rawSchema.$ref
    ? resolveRef(rawSchema, rootSchema || rawSchema)
    : rawSchema;

  const root = rootSchema || schema;

  // allOf → merge into single schema, then re-dispatch
  if (schema.allOf && schema.allOf.length > 0) {
    const merged = mergeAllOf(schema.allOf);
    return (
      <SchemaForm
        schema={merged}
        values={values}
        onChange={onChange}
        path={path}
        required={required}
        rootSchema={root}
      />
    );
  }

  // oneOf / anyOf → branch selector
  if (schema.oneOf || schema.anyOf) {
    return (
      <OneOfField
        schema={schema}
        values={values}
        onChange={onChange}
        path={path}
        required={required}
        rootSchema={root}
      />
    );
  }

  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;

  // object with properties → recursive object renderer
  if (type === "object" || schema.properties) {
    return (
      <ObjectField
        schema={schema}
        values={values}
        onChange={onChange}
        path={path}
        required={required}
        rootSchema={root}
      />
    );
  }

  // array → list with add/remove
  if (type === "array") {
    return (
      <ArrayField
        schema={schema}
        values={values}
        onChange={onChange}
        path={path}
        required={required}
        rootSchema={root}
      />
    );
  }

  // primitive: string, number, integer, boolean, enum, const
  return (
    <PrimitiveField
      schema={schema}
      values={values}
      onChange={onChange}
      path={path}
      required={required}
      rootSchema={root}
    />
  );
}
