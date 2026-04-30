"use client";

import { JSONSchemaProperty } from "./types";
import { detectDiscriminatorKey, getDiscriminatorValue, resolveSchema } from "./utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import SchemaForm from "./index";
import { useTranslation } from "react-i18next";

interface OneOfFieldProps {
  variants: JSONSchemaProperty[];
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  rootSchema: JSONSchemaProperty;
}

export default function OneOfField({
  variants,
  value,
  onChange,
  rootSchema,
}: OneOfFieldProps) {
  const { t } = useTranslation("admin");
  const discriminatorKey = detectDiscriminatorKey(variants);

  const options = variants.map((v, i) => ({
    label:
      v.title ??
      (discriminatorKey
        ? getDiscriminatorValue(v, discriminatorKey)
        : t("airbyteConnector.optionLabel", { index: i + 1 })),
    value: String(i),
  }));

  const selectedIndex = (() => {
    if (!discriminatorKey) return 0;
    const currentVal = value?.[discriminatorKey];
    const idx = variants.findIndex((v) => {
      const prop = v.properties?.[discriminatorKey];
      return (
        prop?.const === currentVal ||
        (Array.isArray(prop?.enum) && prop.enum![0] === currentVal)
      );
    });
    return idx >= 0 ? idx : 0;
  })();

  const selectedVariant = resolveSchema(variants[selectedIndex] ?? {}, rootSchema);

  const handleVariantChange = (indexStr: string) => {
    const idx = parseInt(indexStr, 10);
    const variant = resolveSchema(variants[idx] ?? {}, rootSchema);

    const newValue: Record<string, unknown> = {};
    if (discriminatorKey && variant.properties?.[discriminatorKey]) {
      const prop = variant.properties[discriminatorKey];
      newValue[discriminatorKey] =
        prop.const ?? (Array.isArray(prop.enum) ? prop.enum[0] : undefined);
    }
    if (variant.properties) {
      Object.keys(variant.properties).forEach((k) => {
        if (k !== discriminatorKey && value?.[k] !== undefined) {
          newValue[k] = value[k];
        }
      });
    }
    onChange(newValue);
  };

  return (
    <div className="space-y-3">
      <Select
        value={String(selectedIndex)}
        onValueChange={handleVariantChange}
      >
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {selectedVariant.properties && (
        <div className="pl-3 border-l border-border space-y-4">
          {Object.entries(selectedVariant.properties)
            .filter(([k]) => k !== discriminatorKey)
            .map(([key, propSchema]) => {
              if (propSchema.airbyte_hidden) return null;
              return (
                <SchemaForm
                  key={key}
                  schema={propSchema}
                  value={(value?.[key] ?? propSchema.default) as Record<string, unknown>}
                  onChange={(v) => onChange({ ...(value ?? {}), [key]: v })}
                  rootSchema={rootSchema}
                  fieldKey={key}
                  required={selectedVariant.required?.includes(key)}
                />
              );
            })}
        </div>
      )}
    </div>
  );
}
