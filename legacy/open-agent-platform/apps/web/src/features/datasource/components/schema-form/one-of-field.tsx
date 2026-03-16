"use client";

import { useState, useEffect, useCallback } from "react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SchemaFormProps } from "./types";
import { SchemaForm } from "./schema-form";
import { buildOneOfOptions, detectOneOfBranch } from "./utils";

/**
 * Renders a dropdown selector for oneOf / anyOf branches.
 * When the user selects a branch, the sub-schema is rendered recursively.
 */
export function OneOfField({
  schema,
  values,
  onChange,
  path = [],
  required = false,
  rootSchema,
}: SchemaFormProps) {
  const branches = schema.oneOf || schema.anyOf || [];
  const options = buildOneOfOptions(branches);

  // Detect current branch from existing values
  const initialBranch = detectOneOfBranch(options, values);
  const [selectedIndex, setSelectedIndex] = useState<number>(initialBranch);

  const selectedOption = options[selectedIndex];

  // Re-detect on external value changes
  useEffect(() => {
    const detected = detectOneOfBranch(options, values);
    if (detected !== selectedIndex) {
      setSelectedIndex(detected);
    }
  }, [values]);

  const handleBranchChange = useCallback(
    (indexStr: string) => {
      const newIndex = parseInt(indexStr);
      if (newIndex === selectedIndex) return;

      setSelectedIndex(newIndex);

      const newOption = options[newIndex];
      // Build initial values for the new branch
      const newValues: Record<string, any> = {};

      // Set discriminator const values
      if (newOption.discriminator) {
        newValues[newOption.discriminator.key] = newOption.discriminator.value;
      }

      // Copy over compatible fields and set defaults
      if (newOption.schema.properties) {
        for (const [key, propSchema] of Object.entries(newOption.schema.properties)) {
          if (propSchema.const !== undefined) {
            newValues[key] = propSchema.const;
          } else if (
            values &&
            typeof values === "object" &&
            values[key] !== undefined
          ) {
            // Carry over existing value if field exists in new branch
            newValues[key] = values[key];
          } else if (propSchema.default !== undefined) {
            newValues[key] = propSchema.default;
          }
        }
      }

      onChange(newValues);
    },
    [selectedIndex, options, values, onChange],
  );

  if (options.length === 0) return null;

  // If only one option, render it directly without selector
  if (options.length === 1) {
    return (
      <SchemaForm
        schema={options[0].schema}
        values={values}
        onChange={onChange}
        path={path}
        required={required}
        rootSchema={rootSchema}
      />
    );
  }

  const key = path[path.length - 1] || "";
  const label = schema.title || key;

  return (
    <div className="space-y-3">
      {/* Branch selector */}
      <div className="grid gap-1.5">
        {!schema.title && label && (
          <Label className="text-sm">
            {label}
            {required && <span className="text-red-500 ml-1">*</span>}
          </Label>
        )}
        <Select
          value={selectedIndex.toString()}
          onValueChange={handleBranchChange}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select type..." />
          </SelectTrigger>
          <SelectContent>
            {options.map((opt) => (
              <SelectItem key={opt.index} value={opt.index.toString()}>
                {opt.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Render selected branch */}
      {selectedOption && (
        <div className="border-l-2 border-muted pl-4 space-y-3">
          <SchemaForm
            schema={selectedOption.schema}
            values={values}
            onChange={onChange}
            path={path}
            required={required}
            rootSchema={rootSchema}
          />
        </div>
      )}
    </div>
  );
}
