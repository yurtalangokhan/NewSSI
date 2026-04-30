"use client";

import { JSONSchemaProperty } from "./types";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import PasswordInputTypeIn from "@/refresh-components/inputs/PasswordInputTypeIn";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface PrimitiveFieldProps {
  schema: JSONSchemaProperty;
  value: unknown;
  onChange: (value: unknown) => void;
  id?: string;
  required?: boolean;
}

export default function PrimitiveField({
  schema,
  value,
  onChange,
  id,
  required,
}: PrimitiveFieldProps) {
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  const isSecret = schema.airbyte_secret === true;
  const placeholder =
    Array.isArray(schema.examples) && schema.examples.length > 0
      ? `e.g. ${schema.examples[0]}`
      : schema.default !== undefined
        ? String(schema.default)
        : "";

  // Enum / select
  if (schema.enum && schema.enum.length > 0) {
    return (
      <Select
        value={value !== undefined ? String(value) : ""}
        onValueChange={(v) => onChange(v)}
      >
        <SelectTrigger>
          <SelectValue placeholder="Select an option..." />
        </SelectTrigger>
        <SelectContent>
          {schema.enum.map((v) => (
            <SelectItem key={String(v)} value={String(v)}>
              {String(v)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  // Boolean → checkbox
  if (type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <Checkbox
          checked={value === true}
          onCheckedChange={(checked) => onChange(checked)}
          id={id}
        />
        {schema.description && (
          <label htmlFor={id} className="text-xs text-text-03 cursor-pointer">
            {schema.description}
          </label>
        )}
      </div>
    );
  }

  // Number / integer
  if (type === "number" || type === "integer") {
    return (
      <InputTypeIn
        type="number"
        value={value !== undefined ? String(value) : ""}
        onChange={(e) => {
          const n = parseFloat(e.target.value);
          onChange(isNaN(n) ? undefined : n);
        }}
        placeholder={placeholder}
        min={schema.minimum}
        max={schema.maximum}
      />
    );
  }

  // Multiline string
  const isMultiline =
    schema.format === "textarea" ||
    (schema.description?.toLowerCase().includes("multiline") ?? false);

  if (isMultiline && !isSecret) {
    return (
      <InputTextArea
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={4}
      />
    );
  }

  // Secret / password
  if (isSecret) {
    return (
      <PasswordInputTypeIn
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
      />
    );
  }

  // Default: text input
  return (
    <InputTypeIn
      type="text"
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      required={required}
    />
  );
}
