"use client";

import { JSONSchemaProperty } from "./types";
import { detectDiscriminatorKey, mergeAllOf, resolveSchema } from "./utils";
import PrimitiveField from "./PrimitiveField";
import ObjectField from "./ObjectField";
import ArrayField from "./ArrayField";
import OneOfField from "./OneOfField";

interface SchemaFormProps {
  schema: JSONSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  rootSchema?: JSONSchemaProperty;
  /** Key name of this field within its parent (used for label fallback) */
  fieldKey?: string;
  required?: boolean;
}

export default function SchemaForm({
  schema: rawSchema,
  value,
  onChange,
  rootSchema,
  fieldKey,
  required,
}: SchemaFormProps) {
  // The root schema is used for $ref resolution
  const root = rootSchema ?? rawSchema;

  // Resolve $ref
  let schema = resolveSchema(rawSchema, root);

  // Merge allOf
  if (schema.allOf) {
    schema = mergeAllOf(schema.allOf, root);
  }

  // Skip hidden fields
  if (schema.airbyte_hidden) return null;

  const label = schema.title ?? (fieldKey ? formatKey(fieldKey) : undefined);
  const id = fieldKey ?? label ?? "field";

  // Render label + field wrapper
  const renderField = () => {
    // oneOf / anyOf with discriminator → OneOfField
    const variants = schema.oneOf ?? schema.anyOf;
    if (variants && variants.length > 0) {
      const resolved = variants.map((v) => resolveSchema(v, root));
      const hasDiscriminator = detectDiscriminatorKey(resolved) !== null;
      if (hasDiscriminator) {
        return (
          <OneOfField
            variants={resolved}
            value={(value as Record<string, unknown>) ?? {}}
            onChange={onChange as (v: Record<string, unknown>) => void}
            rootSchema={root}
          />
        );
      }
      // Fallback: treat first variant as the schema
      return (
        <SchemaForm
          schema={resolved[0] ?? {}}
          value={value}
          onChange={onChange}
          rootSchema={root}
          fieldKey={fieldKey}
          required={required}
        />
      );
    }

    const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;

    // Object
    if (type === "object" || schema.properties) {
      return (
        <ObjectField
          schema={schema}
          value={(value as Record<string, unknown>) ?? {}}
          onChange={onChange as (v: Record<string, unknown>) => void}
          rootSchema={root}
        />
      );
    }

    // Array
    if (type === "array") {
      return (
        <ArrayField
          schema={schema}
          value={(value as unknown[]) ?? []}
          onChange={onChange as (v: unknown[]) => void}
        />
      );
    }

    // Primitive (string, number, boolean, enum)
    return (
      <PrimitiveField
        schema={schema}
        value={value}
        onChange={onChange}
        id={id}
        required={required}
      />
    );
  };

  // Top-level call (no fieldKey) renders just the root object without a wrapper label
  if (!fieldKey) {
    return <div className="space-y-4">{renderField()}</div>;
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <label htmlFor={id} className="text-sm font-medium text-text-02">
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
      </div>

      {schema.description && (
        <p className="text-xs text-text-03">{schema.description}</p>
      )}

      {renderField()}
    </div>
  );
}

function formatKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^\w/, (c) => c.toUpperCase());
}
