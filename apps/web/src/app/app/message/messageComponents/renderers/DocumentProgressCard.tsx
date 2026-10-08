"use client";

import { useTranslation } from "react-i18next";
import { SvgCheck } from "@/icons";
import {
  keyedChanges,
  type GenerationState,
} from "@/app/app/message/messageComponents/renderers/documentGenerationState";
import { FileIcon } from "@/components/icons/icons";
import { useAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";

// Uneven widths on purpose: a page of prose being written, not a loading bar.
const LINE_WIDTHS = ["w-[92%]", "w-[78%]", "w-[85%]", "w-[60%]"];
const SHIMMER =
  "animate-shimmer bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--shimmer-base)_10%,var(--shimmer-highlight)_40%,var(--shimmer-base)_70%)]";

interface DocumentProgressCardProps {
  state: GenerationState;
}

function fileTitle(
  filename: string | null,
  format: string | null,
  fallback: string
) {
  if (!filename) return fallback;
  return format && !filename.toLowerCase().endsWith(`.${format.toLowerCase()}`)
    ? `${filename}.${format}`
    : filename;
}

export function DocumentProgressCard({ state }: DocumentProgressCardProps) {
  const { t } = useTranslation();
  const isEdit = state.operation === "edit" || state.operation === "rewrite";
  const { data: document } = useAuthoredDocument(
    isEdit ? state.documentId : null
  );
  const filename = fileTitle(
    state.filename,
    state.format,
    t("documentGeneration.untitled", "Document")
  );

  const writing = t("documentGeneration.writing", "Writing document...");
  const status = (() => {
    switch (state.phase) {
      case "applying":
        return state.total
          ? t("documentProgress.applying", {
              applied: state.applied ?? 0,
              total: state.total,
            })
          : t("documentProgress.applyingUnknown");
      case "validating":
        return t("documentProgress.validating");
      case "rendering":
        return isEdit && state.format
          ? t("documentProgress.rendering", {
              format: state.format.toUpperCase(),
            })
          : t("documentGeneration.rendering", "Preparing file...");
      default:
        return state.chars > 0
          ? t("documentGeneration.progress", {
              label: writing,
              chars: state.chars.toLocaleString(),
              defaultValue: "{{label}} ({{chars}} characters)",
            })
          : writing;
    }
  })();

  const title = isEdit
    ? document
      ? t("documentProgress.title", {
          revision: document.head_revision_no + 1,
        })
      : t("documentProgress.titleNew")
    : filename;

  return (
    <div
      className="flex flex-col border bg-background-tint-00 rounded-12 p-1 gap-2 my-1 w-full max-w-[22rem] animate-fade-in-scale"
      role="status"
      aria-live="polite"
      aria-label={status}
      data-testid="document-generation-skeleton"
    >
      <div className="flex items-center gap-1">
        <div className="p-2 bg-background-tint-01 rounded-08 animate-subtle-pulse">
          <FileIcon size={20} />
        </div>
        <div className="flex flex-col px-2 min-w-0">
          <Text as="p" secondaryAction className="truncate">
            {title}
          </Text>
          {isEdit && (
            <Text as="p" secondaryBody text03 className="truncate">
              {filename}
            </Text>
          )}
        </div>
      </div>

      {state.changes.length > 0 ? (
        <ol className="flex flex-col gap-1 px-3">
          {keyedChanges(state.changes).map(({ change, key }) => (
            <li key={key} className="flex items-center gap-2">
              <SvgCheck size={12} className="text-text-03" />
              <Text as="span" secondaryBody text04>
                {t(`documentCard.change.${change.change}`, {
                  label: change.label,
                })}
              </Text>
            </li>
          ))}
        </ol>
      ) : (
        <div className="flex flex-col gap-2 px-3 pt-1" aria-hidden="true">
          {LINE_WIDTHS.map((width, index) => (
            <div
              key={width}
              className={cn(
                "h-2 rounded-04 bg-background-tint-02",
                SHIMMER,
                width
              )}
              style={{ animationDelay: `${index * 120}ms`, opacity: 0.35 }}
            />
          ))}
        </div>
      )}

      <Text
        as="p"
        secondaryBody
        text03
        className={cn("px-3 pb-2 bg-clip-text text-transparent", SHIMMER)}
      >
        {status}
      </Text>
    </div>
  );
}
