"use client";

import { JSONSchemaProperty } from "./types";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { useTranslation } from "react-i18next";

interface ArrayFieldProps {
  schema: JSONSchemaProperty;
  value: unknown[];
  onChange: (value: unknown[]) => void;
}

export default function ArrayField({ schema, value, onChange }: ArrayFieldProps) {
  const { t } = useTranslation("admin");
  const items = Array.isArray(value) ? value : [];
  const itemSchema = Array.isArray(schema.items) ? schema.items[0] : schema.items;
  const isStringArray = !itemSchema || (itemSchema as JSONSchemaProperty).type === "string";

  const handleAdd = () => onChange([...items, ""]);
  const handleRemove = (i: number) => onChange(items.filter((_, idx) => idx !== i));
  const handleChange = (i: number, v: string) =>
    onChange(items.map((item, idx) => (idx === i ? v : item)));

  return (
    <div className="space-y-2">
      {items.map((item, i) => (
        <div key={`item-${i}`} className="flex gap-2 items-center">
          <InputTypeIn
            type="text"
            value={typeof item === "string" ? item : isStringArray ? "" : JSON.stringify(item)}
            onChange={(e) => handleChange(i, e.target.value)}
            className="flex-1"
            placeholder={isStringArray ? t("arrayField.itemIndex", { index: i + 1 }) : undefined}
          />
          <Button onClick={() => handleRemove(i)} size="md">
            {t("arrayField.remove")}
          </Button>
        </div>
      ))}
      <Button onClick={handleAdd} size="md">
        {t("arrayField.addItem")}
      </Button>
    </div>
  );
}
