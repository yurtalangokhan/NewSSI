"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { SchemaFormProps } from "./types";
import { isSecret } from "./utils";
import { useEffect } from "react";

/**
 * Renders a single primitive field: string, number, integer, boolean.
 * Also handles enum, const, secret, and various string formats.
 */
export function PrimitiveField({
  schema,
  values: value,
  onChange,
  path = [],
  required = false,
}: SchemaFormProps) {
  const key = path[path.length - 1] || "";
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  const label = schema.title || key;

  // Auto-set const values
  useEffect(() => {
    if (schema.const !== undefined && value !== schema.const) {
      onChange(schema.const);
    }
  }, [schema.const]);

  // Hidden const field
  if (schema.const !== undefined) {
    return null;
  }

  // Enum → Select dropdown
  if (schema.enum && schema.enum.length > 0) {
    return (
      <div className="grid gap-1.5">
        <Label className="flex items-center gap-1 text-sm">
          {label}
          {required && <span className="text-red-500">*</span>}
        </Label>
        {schema.description && (
          <p className="text-xs text-muted-foreground">{schema.description}</p>
        )}
        <Select
          value={value?.toString() ?? ""}
          onValueChange={(v) => onChange(type === "integer" ? parseInt(v) : type === "number" ? parseFloat(v) : v)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select..." />
          </SelectTrigger>
          <SelectContent>
            {schema.enum.map((opt: any) => (
              <SelectItem key={String(opt)} value={String(opt)}>
                {String(opt)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  // Boolean → Switch
  if (type === "boolean") {
    return (
      <div className="flex items-center justify-between rounded-md border p-3">
        <div className="space-y-0.5">
          <Label className="text-sm">{label}</Label>
          {schema.description && (
            <p className="text-xs text-muted-foreground">{schema.description}</p>
          )}
        </div>
        <Switch
          checked={!!value}
          onCheckedChange={(checked) => onChange(checked)}
        />
      </div>
    );
  }

  // Number / Integer
  if (type === "number" || type === "integer") {
    return (
      <div className="grid gap-1.5">
        <Label className="flex items-center gap-1 text-sm">
          {label}
          {required && <span className="text-red-500">*</span>}
        </Label>
        {schema.description && (
          <p className="text-xs text-muted-foreground">{schema.description}</p>
        )}
        <Input
          type="number"
          min={schema.minimum}
          max={schema.maximum}
          step={type === "integer" ? 1 : schema.multipleOf ?? "any"}
          placeholder={schema.examples?.[0]?.toString() ?? ""}
          value={value ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              onChange(undefined);
            } else {
              onChange(type === "integer" ? parseInt(raw) : parseFloat(raw));
            }
          }}
        />
      </div>
    );
  }

  // String (default)
  const inputType = isSecret(schema, key)
    ? "password"
    : schema.format === "uri" || schema.format === "url"
      ? "url"
      : "text";

  const isMultiline =
    schema.format === "textarea" ||
    (schema.maxLength && schema.maxLength > 256);

  return (
    <div className="grid gap-1.5">
      <Label className="flex items-center gap-1 text-sm">
        {label}
        {required && <span className="text-red-500">*</span>}
      </Label>
      {schema.description && (
        <p className="text-xs text-muted-foreground">{schema.description}</p>
      )}
      {isMultiline ? (
        <textarea
          className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder={schema.examples?.[0]?.toString() ?? ""}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Input
          type={inputType}
          placeholder={schema.examples?.[0]?.toString() ?? schema.default?.toString() ?? ""}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}
