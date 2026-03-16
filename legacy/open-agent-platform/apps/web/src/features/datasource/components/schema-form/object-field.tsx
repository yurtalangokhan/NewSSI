"use client";

import { Label } from "@/components/ui/label";
import type { SchemaFormProps } from "./types";
import { SchemaForm } from "./schema-form";
import { getFieldOrder, isRequired, isHidden } from "./utils";
import { useEffect } from "react";

/**
 * Renders all properties of a JSON Schema object type.
 * Each property is rendered via a recursive SchemaForm call.
 */
export function ObjectField({
  schema,
  values,
  onChange,
  path = [],
  required = false,
  rootSchema,
}: SchemaFormProps) {
  const currentValues = values && typeof values === "object" ? values : {};
  const properties = schema.properties || {};
  const orderedKeys = getFieldOrder(schema);

  // Initialize defaults for properties that have them
  useEffect(() => {
    const updates: Record<string, any> = {};
    let hasUpdate = false;

    for (const key of orderedKeys) {
      const propSchema = properties[key];
      if (!propSchema) continue;
      if (currentValues[key] !== undefined) continue;

      // Set const values
      if (propSchema.const !== undefined) {
        updates[key] = propSchema.const;
        hasUpdate = true;
      }
      // Set defaults
      else if (propSchema.default !== undefined) {
        updates[key] = propSchema.default;
        hasUpdate = true;
      }
    }

    if (hasUpdate) {
      onChange({ ...currentValues, ...updates });
    }
  }, []);

  function handlePropertyChange(key: string, val: any) {
    onChange({ ...currentValues, [key]: val });
  }

  return (
    <div className="space-y-4">
      {orderedKeys.map((key) => {
        const propSchema = properties[key];
        if (!propSchema) return null;
        if (isHidden(propSchema)) return null;

        const propRequired = isRequired(key, schema);

        // If the property is a top-level group (object/oneOf), render with a title
        const isGroup =
          propSchema.type === "object" ||
          propSchema.oneOf ||
          propSchema.anyOf;

        return (
          <div key={key}>
            {isGroup && propSchema.title && (
              <div className="mb-2">
                <Label className="text-sm font-medium">
                  {propSchema.title}
                  {propRequired && <span className="text-red-500 ml-1">*</span>}
                </Label>
                {propSchema.description && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {propSchema.description}
                  </p>
                )}
              </div>
            )}
            <SchemaForm
              schema={propSchema}
              values={currentValues[key]}
              onChange={(val) => handlePropertyChange(key, val)}
              path={[...path, key]}
              required={propRequired}
              rootSchema={rootSchema}
            />
          </div>
        );
      })}
    </div>
  );
}
