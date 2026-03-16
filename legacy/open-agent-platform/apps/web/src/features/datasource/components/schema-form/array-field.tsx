"use client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Plus, Trash2 } from "lucide-react";
import type { SchemaFormProps } from "./types";
import { SchemaForm } from "./schema-form";
import { getDefaultValue } from "./utils";

/**
 * Renders an array-type schema.
 * Each item in the array is rendered via a recursive SchemaForm call.
 * Supports add/remove item operations with min/max constraints.
 */
export function ArrayField({
  schema,
  values,
  onChange,
  path = [],
  required = false,
  rootSchema,
}: SchemaFormProps) {
  const items = Array.isArray(values) ? values : [];
  const itemSchema = schema.items || { type: "string" };
  const minItems = schema.minItems ?? 0;
  const maxItems = schema.maxItems ?? Infinity;
  const key = path[path.length - 1] || "";
  const label = schema.title || key;

  function handleAddItem() {
    if (items.length >= maxItems) return;
    const defaultVal = getDefaultValue(itemSchema);
    onChange([...items, defaultVal]);
  }

  function handleRemoveItem(index: number) {
    if (items.length <= minItems) return;
    onChange(items.filter((_, i) => i !== index));
  }

  function handleItemChange(index: number, val: any) {
    const updated = [...items];
    updated[index] = val;
    onChange(updated);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label className="text-sm">
          {label}
          {required && <span className="text-red-500 ml-1">*</span>}
        </Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAddItem}
          disabled={items.length >= maxItems}
          className="gap-1"
        >
          <Plus className="h-3 w-3" />
          Add
        </Button>
      </div>
      {schema.description && (
        <p className="text-xs text-muted-foreground">{schema.description}</p>
      )}

      {items.length === 0 && (
        <p className="text-xs text-muted-foreground italic py-2">
          No items. Click &quot;Add&quot; to add one.
        </p>
      )}

      {items.map((item, index) => (
        <div
          key={index}
          className="flex gap-2 items-start border rounded-md p-3"
        >
          <div className="flex-1">
            <SchemaForm
              schema={itemSchema}
              values={item}
              onChange={(val) => handleItemChange(index, val)}
              path={[...path, index.toString()]}
              rootSchema={rootSchema}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => handleRemoveItem(index)}
            disabled={items.length <= minItems}
            className="shrink-0 h-8 w-8 text-destructive"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
    </div>
  );
}
