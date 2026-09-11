/**
 * Extracted from Task 26's `TemplateNode.tsx` (was a private
 * `RenderInputParameters`) so Task 27's `NodeInspector` (side panel) and
 * `TemplateNode` (inline, on-canvas) render a node's fields through the
 * exact same component — the brief's "no-fork" rule (27.4): if a field
 * looks different inline vs. in the panel, that's a prop on this
 * component, not a second implementation.
 *
 * `onFieldBlur` is optional and unused by `TemplateNode` — it exists for
 * `NodeInspector`'s debounced-snapshot requirement (27.6): a keystroke
 * must not be its own undo step, so the panel snapshots once per edit
 * session and resets on blur. Inline canvas edits (this task's scope
 * doesn't extend to them) still take no snapshot at all — see
 * task-27-report.md for why that inconsistency is disclosed, not fixed
 * here.
 */

"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import Text from "@/refresh-components/texts/Text";
import { SvgInfo } from "@opal/icons";
import { useTranslation } from "react-i18next";
import { FIELD_RENDERERS } from "../fields";
import type {
  ComponentTemplate,
  InputField,
  TableColumn,
} from "../types/componentTemplate";
import { visibleInputs } from "../utils/templateSchema";

function FieldRow({
  fieldKey,
  field,
  value,
  onChange,
  onBlur,
  columns,
  allValues,
  componentType,
}: {
  fieldKey: string;
  field: InputField;
  value: unknown;
  onChange: (value: unknown) => void;
  onBlur?: () => void;
  columns?: TableColumn[];
  allValues?: Record<string, unknown>;
  componentType?: string;
}) {
  const { t } = useTranslation();
  const Renderer = FIELD_RENDERERS[field.type];
  const infoTooltip = field.info
    ? t(
        componentType
          ? [
              `flowCanvas.fields.infos.${componentType}.${fieldKey}`,
              `flowCanvas.fields.infos.${fieldKey}`,
            ]
          : `flowCanvas.fields.infos.${fieldKey}`,
        field.info
      )
    : undefined;

  return (
    <div className="flex flex-col gap-1.5" onBlur={onBlur}>
      {/* upstream NodeInputField:161-192 — label, a red asterisk when
          required, then a small info glyph carrying the tooltip. */}
      <div className="flex w-full items-center text-sm">
        <span className="truncate font-medium text-canvas-fg">
          {t(
            componentType
              ? [
                  `flowCanvas.fields.names.${componentType}.${fieldKey}`,
                  `flowCanvas.fields.names.${fieldKey}`,
                ]
              : `flowCanvas.fields.names.${fieldKey}`,
            field.display_name
          )}
          {field.required && <span className="text-destructive">*</span>}
        </span>
        {field.info && (
          <SimpleTooltip tooltip={infoTooltip}>
            <span className="ml-1 cursor-help text-muted-foreground">
              <SvgInfo className="h-3 w-3" />
            </span>
          </SimpleTooltip>
        )}
      </div>
      <Renderer
        fieldKey={fieldKey}
        field={field}
        value={value}
        onChange={onChange}
        columns={columns}
        allValues={allValues}
      />
    </div>
  );
}

export type NodeFieldListProps = {
  template: ComponentTemplate;
  values: Record<string, unknown>;
  onFieldChange: (key: string, value: unknown) => void;
  onFieldBlur?: (key: string) => void;
  excludedKeys?: string[];
  className?: string;
};

export function NodeFieldList({
  template,
  values,
  onFieldChange,
  onFieldBlur,
  excludedKeys,
  className,
}: NodeFieldListProps) {
  const { t } = useTranslation();
  const excluded = new Set(excludedKeys ?? []);
  const visible = visibleInputs(template, values);
  const entries = Object.entries(visible).filter(([key]) => !excluded.has(key));
  const basic = entries.filter(([, f]) => !f.advanced);
  const advanced = entries.filter(([, f]) => f.advanced);

  return (
    <div className={className ?? "flex flex-col gap-2"}>
      {basic.map(([key, field]) => (
        <FieldRow
          key={key}
          fieldKey={key}
          field={field}
          value={key in values ? values[key] : field.value}
          onChange={(v) => onFieldChange(key, v)}
          onBlur={onFieldBlur ? () => onFieldBlur(key) : undefined}
          columns={field.columns ?? undefined}
          allValues={values}
          componentType={template.type}
        />
      ))}
      {advanced.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="w-full px-0.5 py-1 text-left">
            <Text text03 secondaryBody>
              {t("flowCanvas.inspector.advanced", "Advanced")}
            </Text>
          </CollapsibleTrigger>
          <CollapsibleContent className="flex flex-col gap-2">
            {advanced.map(([key, field]) => (
              <FieldRow
                key={key}
                fieldKey={key}
                field={field}
                value={key in values ? values[key] : field.value}
                onChange={(v) => onFieldChange(key, v)}
                onBlur={onFieldBlur ? () => onFieldBlur(key) : undefined}
                columns={field.columns ?? undefined}
                allValues={values}
                componentType={template.type}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
