/**
 * The "real" diff for a single field whose value was too long for
 * `FlowDiffList`'s inline bullet — a wide git-style side-by-side view
 * (old left, new right, word-level highlighting) floating over the
 * canvas itself rather than squeezed into VersionHistoryPanel's 288px
 * width. `FlowDiffList`'s "X changed" bullets hand off to this via
 * `onExpandField`; VersionHistoryPanel owns which field (if any) is
 * currently shown here.
 */

"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { diffWords } from "diff";
import Text from "@/refresh-components/texts/Text";
import IconButton from "@/refresh-components/buttons/IconButton";
import { cn } from "@/lib/utils";
import { SvgX } from "@opal/icons";
import type { ExpandableField } from "./FlowDiffList";

export type FieldDiffOverlayProps = {
  field: ExpandableField;
  onClose: () => void;
};

function formatValue(value: unknown, emptyLabel: string): string {
  if (value === undefined || value === null) return emptyLabel;
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function FieldDiffOverlay({ field, onClose }: FieldDiffOverlayProps) {
  const { t } = useTranslation();
  const emptyLabel = t("flowCanvas.versionHistory.diff.emptyValue", "(empty)");
  const oldText = formatValue(field.oldValue, emptyLabel);
  const newText = formatValue(field.newValue, emptyLabel);
  const parts = useMemo(() => diffWords(oldText, newText), [oldText, newText]);

  return (
    <div
      className="langflow-canvas absolute inset-6 z-40 flex flex-col overflow-hidden rounded-xl border border-canvas-border bg-canvas-panel shadow-2xl"
      data-testid="field-diff-overlay"
    >
      <div className="flex shrink-0 items-center justify-between border-b border-canvas-border px-4 py-2.5">
        <Text mainUiBody className="font-semibold">
          {field.label}
        </Text>
        <IconButton
          icon={SvgX}
          tooltip={t(
            "flowCanvas.versionHistory.diff.closeOverlay",
            "Close diff"
          )}
          aria-label={t(
            "flowCanvas.versionHistory.diff.closeOverlay",
            "Close diff"
          )}
          onClick={onClose}
          data-testid="field-diff-overlay-close"
        />
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-2 overflow-auto text-sm">
        <div className="whitespace-pre-wrap break-words p-4">
          {parts
            .filter((p) => !p.added)
            .map((p, i) => (
              <span
                key={i}
                className={cn(
                  p.removed && "bg-destructive/20 text-destructive line-through"
                )}
              >
                {p.value}
              </span>
            ))}
        </div>
        <div className="whitespace-pre-wrap break-words border-l border-canvas-border p-4">
          {parts
            .filter((p) => !p.removed)
            .map((p, i) => (
              <span
                key={i}
                className={cn(
                  p.added && "bg-theme-green-01 text-theme-green-05"
                )}
              >
                {p.value}
              </span>
            ))}
        </div>
      </div>
    </div>
  );
}
