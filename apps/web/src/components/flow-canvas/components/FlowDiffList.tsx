/**
 * The compact bullet list for one `diffFlowSpecs` result — meant to sit
 * inline in a narrow accordion (VersionHistoryPanel's own width), not a
 * wide panel: short field values render right in the bullet, long ones
 * just name the field and hand off to `onExpandField` so the caller can
 * open the real side-by-side diff somewhere with actual room (see
 * `FieldDiffOverlay`), rather than trying to cram a git diff into a
 * 288px-wide sidebar.
 */

"use client";

import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import {
  SvgArrowRight,
  SvgChevronRight,
  SvgEdit,
  SvgMinus,
  SvgPlus,
  SvgRefreshCw,
} from "@opal/icons";
import type { FlowDiffEntry } from "../utils/compile";

export type ExpandableField = {
  label: string;
  oldValue: unknown;
  newValue: unknown;
};

export type FlowDiffListProps = {
  entries: FlowDiffEntry[];
  onExpandField: (field: ExpandableField) => void;
};

/** Inline in the bullet if short enough to read as one line; otherwise
 * the bullet just names the field and hands off to the canvas-overlay
 * diff. A prompt's worth of text has no business sitting inline in a
 * list of one-liners, let alone a 288px-wide panel. */
function isShortValue(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === "object") return false;
  const s = String(value);
  return s.length <= 60 && !s.includes("\n");
}

function formatValue(value: unknown, emptyLabel: string): string {
  if (value === undefined || value === null) return emptyLabel;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DiffRow({
  entry,
  onExpandField,
}: {
  entry: FlowDiffEntry;
  onExpandField: (field: ExpandableField) => void;
}) {
  const { t } = useTranslation();
  const emptyLabel = t("flowCanvas.versionHistory.diff.emptyValue", "(empty)");

  switch (entry.kind) {
    case "node-added":
      return (
        <li className="flex items-start gap-1.5">
          <SvgPlus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-theme-green-05" />
          <Text secondaryBody>
            {t(
              "flowCanvas.versionHistory.diff.nodeAdded",
              "{{type}} node added",
              { type: entry.nodeType }
            )}
          </Text>
        </li>
      );
    case "node-removed":
      return (
        <li className="flex items-start gap-1.5">
          <SvgMinus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
          <Text secondaryBody>
            {t(
              "flowCanvas.versionHistory.diff.nodeRemoved",
              "{{type}} node removed",
              { type: entry.nodeType }
            )}
          </Text>
        </li>
      );
    case "edge-added":
      return (
        <li className="flex items-start gap-1.5">
          <SvgPlus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-theme-green-05" />
          <Text secondaryBody className="flex flex-wrap items-center gap-1">
            {t(
              "flowCanvas.versionHistory.diff.connectionAdded",
              "Connection added:"
            )}
            <span className="font-medium">{entry.sourceType}</span>
            <SvgArrowRight className="h-3 w-3 shrink-0" />
            <span className="font-medium">{entry.targetType}</span>
          </Text>
        </li>
      );
    case "edge-removed":
      return (
        <li className="flex items-start gap-1.5">
          <SvgMinus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
          <Text secondaryBody className="flex flex-wrap items-center gap-1">
            {t(
              "flowCanvas.versionHistory.diff.connectionRemoved",
              "Connection removed:"
            )}
            <span className="font-medium">{entry.sourceType}</span>
            <SvgArrowRight className="h-3 w-3 shrink-0" />
            <span className="font-medium">{entry.targetType}</span>
          </Text>
        </li>
      );
    case "template-upgraded":
      return (
        <li className="flex items-start gap-1.5">
          <SvgRefreshCw className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Text secondaryBody>
            {t(
              "flowCanvas.versionHistory.diff.templateUpgraded",
              "{{type}} updated from template v{{oldVersion}} to v{{newVersion}}",
              {
                type: entry.nodeType,
                oldVersion: entry.oldVersion,
                newVersion: entry.newVersion,
              }
            )}
          </Text>
        </li>
      );
    case "field-changed": {
      const oldStr = formatValue(entry.oldValue, emptyLabel);
      const newStr = formatValue(entry.newValue, emptyLabel);
      const short =
        isShortValue(entry.oldValue) && isShortValue(entry.newValue);
      const label = `${entry.nodeType}.${entry.field}`;
      return (
        <li className="flex items-start gap-1.5">
          <SvgEdit className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          {short ? (
            <Text secondaryBody className="flex flex-wrap items-center gap-1">
              <span className="font-medium">{label}</span>
              <span className="text-destructive line-through">{oldStr}</span>
              <SvgArrowRight className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="text-theme-green-05">{newStr}</span>
            </Text>
          ) : (
            <button
              type="button"
              onClick={() =>
                onExpandField({
                  label,
                  oldValue: entry.oldValue,
                  newValue: entry.newValue,
                })
              }
              className="flex min-w-0 items-center gap-1 text-left hover:underline"
              data-testid={`diff-expand-${entry.nodeId}-${entry.field}`}
            >
              <Text secondaryBody className="truncate font-medium">
                {t(
                  "flowCanvas.versionHistory.diff.fieldChanged",
                  "{{field}} changed",
                  { field: label }
                )}
              </Text>
              <SvgChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </button>
          )}
        </li>
      );
    }
    default:
      return null;
  }
}

export function FlowDiffList({ entries, onExpandField }: FlowDiffListProps) {
  const { t } = useTranslation();

  if (entries.length === 0) {
    return (
      <Text text03 secondaryBody data-testid="version-diff-empty">
        {t("flowCanvas.versionHistory.diff.noChanges", "No changes.")}
      </Text>
    );
  }

  return (
    <ul className="flex w-full flex-col gap-2" data-testid="version-diff-list">
      {entries.map((entry, i) => (
        <DiffRow key={i} entry={entry} onExpandField={onExpandField} />
      ))}
    </ul>
  );
}
