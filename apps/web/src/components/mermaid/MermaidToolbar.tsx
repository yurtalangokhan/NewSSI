"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgCopy, SvgDownload, SvgImage, SvgMaximize2 } from "@/icons";
import Text from "@/refresh-components/texts/Text";

export type MermaidView = "diagram" | "code";

export interface MermaidToolbarActions {
  view: MermaidView;
  onViewChange: (view: MermaidView) => void;
  /** Same copy-and-toast mechanism the error view uses, kept identical across both. */
  onCopy: () => void;
  onDownloadSvg: () => void;
  onDownloadPng: () => void;
  onExpand: () => void;
}

interface MermaidToolbarProps {
  label: string;
  showLabel: boolean;
  /** Null until there is an SVG to act on. */
  actions: MermaidToolbarActions | null;
}

export function MermaidToolbar({
  label,
  showLabel,
  actions,
}: MermaidToolbarProps) {
  const { t } = useTranslation();
  if (!showLabel && !actions) return null;

  return (
    <div
      data-testid="mermaid-toolbar"
      className="flex min-h-9 items-center gap-2 border-b border-border-01 bg-background-tint-01 py-1 pl-3 pr-1"
    >
      {showLabel && (
        <Text secondaryMono text03 nowrap className="truncate">
          {label}
        </Text>
      )}
      {actions && (
        <div className="ml-auto flex items-center gap-1">
          <div
            role="group"
            aria-label={t("mermaid.view")}
            className="flex gap-0.5 rounded-08 bg-background-tint-02 p-0.5"
          >
            <Button
              size="xs"
              variant="select"
              selected={actions.view === "diagram"}
              aria-pressed={actions.view === "diagram"}
              onClick={() => actions.onViewChange("diagram")}
            >
              {t("mermaid.showDiagram")}
            </Button>
            <Button
              size="xs"
              variant="select"
              selected={actions.view === "code"}
              aria-pressed={actions.view === "code"}
              onClick={() => actions.onViewChange("code")}
            >
              {t("mermaid.showCode")}
            </Button>
          </div>
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgCopy}
            tooltip={t("mermaid.copyCode")}
            aria-label={t("mermaid.copyCode")}
            onClick={actions.onCopy}
          />
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgDownload}
            tooltip={t("mermaid.downloadSvg")}
            aria-label={t("mermaid.downloadSvg")}
            onClick={actions.onDownloadSvg}
          />
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgImage}
            tooltip={t("mermaid.downloadPng")}
            aria-label={t("mermaid.downloadPng")}
            onClick={actions.onDownloadPng}
          />
          <Button
            size="sm"
            prominence="tertiary"
            icon={SvgMaximize2}
            tooltip={t("mermaid.expand")}
            aria-label={t("mermaid.expand")}
            onClick={actions.onExpand}
          />
        </div>
      )}
    </div>
  );
}
