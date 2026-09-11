"use client";

import { useMemo } from "react";
import { Button } from "@opal/components";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Switch from "@/refresh-components/inputs/Switch";
import { SvgPlus, SvgTrash } from "@opal/icons";
import type { FieldRendererProps } from "./types";
import type { TableColumn } from "../types/componentTemplate";
import { useTranslation } from "react-i18next";

export type TableRow = Record<string, unknown>;

/**
 * `@tanstack/react-table` was deliberately not used: its headless column-model
 * API pays for sorting/grouping/pagination this field needs none of.
 *
 * Each column carries a `type` (and, for an options column, its `options`),
 * mirroring Langflow's `table_schema`. That matters beyond tidiness: while
 * every cell was a free-text box, a Router operator could be saved as "equal"
 * instead of "equals", and an unknown operator is silently false at run time —
 * so the route just never fired. A dropdown makes the mistake unmakeable.
 *
 * A field with no column metadata still works: the columns are derived from
 * whatever keys the rows already have, every cell free text, as before.
 */
function deriveColumns(
  rows: TableRow[],
  columns?: TableColumn[]
): TableColumn[] {
  if (columns && columns.length > 0) return columns;
  const keys = new Set<string>();
  for (const row of rows) for (const k of Object.keys(row)) keys.add(k);
  const names = keys.size > 0 ? Array.from(keys) : ["value"];
  return names.map((name) => ({ name, display_name: name, type: "str" }));
}

/** The value a freshly added row gets for one column. */
function blankValue(column: TableColumn): unknown {
  if (column.type === "bool") return false;
  if (column.type === "options") return column.options?.[0] ?? "";
  return "";
}

export function TableField({
  value,
  onChange,
  disabled,
  columns,
}: FieldRendererProps) {
  const { t } = useTranslation();
  const rows = Array.isArray(value) ? (value as TableRow[]) : [];
  const resolved = useMemo(() => deriveColumns(rows, columns), [rows, columns]);

  function updateCell(rowIndex: number, column: string, cellValue: unknown) {
    onChange(
      rows.map((r, i) => (i === rowIndex ? { ...r, [column]: cellValue } : r))
    );
  }

  function addRow() {
    onChange([
      ...rows,
      Object.fromEntries(resolved.map((c) => [c.name, blankValue(c)])),
    ]);
  }

  function removeRow(rowIndex: number) {
    onChange(rows.filter((_, i) => i !== rowIndex));
  }

  function renderCell(column: TableColumn, row: TableRow, rowIndex: number) {
    const testId = `table-cell-${column.name}-${rowIndex}`;
    const raw = row[column.name];

    if (column.type === "bool") {
      return (
        <Switch
          checked={raw === true || raw === "True" || raw === "true"}
          onCheckedChange={(next) => updateCell(rowIndex, column.name, next)}
          disabled={disabled}
          data-testid={testId}
        />
      );
    }

    if (
      column.type === "options" &&
      column.options &&
      column.options.length > 0
    ) {
      return (
        <InputSelect
          value={typeof raw === "string" && raw !== "" ? raw : undefined}
          onValueChange={(next) => updateCell(rowIndex, column.name, next)}
          disabled={disabled}
        >
          <InputSelect.Trigger
            data-testid={testId}
            placeholder={t("flowCanvas.fields.table.choose", "Choose...")}
          />
          <InputSelect.Content>
            {column.options.map((option) => (
              <InputSelect.Item key={option} value={option}>
                {option}
              </InputSelect.Item>
            ))}
          </InputSelect.Content>
        </InputSelect>
      );
    }

    return (
      <InputTypeIn
        value={typeof raw === "string" ? raw : raw == null ? "" : String(raw)}
        variant={disabled ? "disabled" : undefined}
        showClearButton={false}
        data-testid={testId}
        onChange={(e) => updateCell(rowIndex, column.name, e.target.value)}
      />
    );
  }

  return (
    <div className="flex w-full flex-col gap-1.5" data-testid="table-field">
      <table className="w-full text-left">
        <thead>
          <tr>
            {resolved.map((c) => (
              <th
                key={c.name}
                className="px-1 pb-1 text-xs font-medium capitalize text-text-03"
              >
                {c.display_name || c.name}
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {resolved.map((c) => (
                <td key={c.name} className="px-1 pb-1">
                  {renderCell(c, row, i)}
                </td>
              ))}
              <td>
                <Button
                  icon={SvgTrash}
                  prominence="tertiary"
                  size="sm"
                  disabled={disabled}
                  onClick={() => removeRow(i)}
                  aria-label={t(
                    "flowCanvas.fields.table.removeRow",
                    "Remove row"
                  )}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button
        icon={SvgPlus}
        prominence="tertiary"
        size="sm"
        disabled={disabled}
        onClick={addRow}
      >
        {t("flowCanvas.fields.table.addRow", "Add row")}
      </Button>
    </div>
  );
}
