"use client";

import { JSONSchemaProperty } from "./types";
import { sortPropertiesByOrder } from "./utils";
import SchemaForm from "./index";

interface ObjectFieldProps {
  schema: JSONSchemaProperty;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  rootSchema: JSONSchemaProperty;
}

export default function ObjectField({
  schema,
  value,
  onChange,
  rootSchema,
}: ObjectFieldProps) {
  if (!schema.properties) return null;

  const sorted = sortPropertiesByOrder(schema.properties);

  return (
    <div className="space-y-4">
      {sorted.map(([key, propSchema]) => {
        if (propSchema.airbyte_hidden) return null;
        return (
          <SchemaForm
            key={key}
            schema={propSchema}
            value={value?.[key] as Record<string, unknown>}
            onChange={(v) => onChange({ ...(value ?? {}), [key]: v })}
            rootSchema={rootSchema}
            fieldKey={key}
            required={schema.required?.includes(key)}
          />
        );
      })}
    </div>
  );
}
