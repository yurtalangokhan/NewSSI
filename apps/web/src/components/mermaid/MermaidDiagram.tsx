"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { toast } from "@/hooks/useToast";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import { MermaidErrorView } from "@/components/mermaid/MermaidErrorView";
import { MermaidPending } from "@/components/mermaid/MermaidPending";
import { MermaidSource } from "@/components/mermaid/MermaidSourceView";
import {
  MermaidToolbar,
  type MermaidToolbarActions,
  type MermaidView,
} from "@/components/mermaid/MermaidToolbar";
import { MermaidViewer } from "@/components/mermaid/MermaidViewer";
import {
  describeMermaidDiagnostic,
  type MermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";
import {
  downloadBlob,
  downloadSvg,
  mermaidFileName,
  svgToPngBlob,
} from "@/components/mermaid/mermaidExport";
import {
  detectDiagramType,
  type MermaidDiagramType,
} from "@/components/mermaid/mermaidSource";
import {
  createSvgScopeId,
  readSvgAccessibleName,
  rescopeSvgIds,
} from "@/components/mermaid/mermaidSvg";
import { sanitizeMermaidSvg } from "@/components/mermaid/mermaidSanitize";
import { useMermaidRender } from "@/components/mermaid/useMermaidRender";
import { useMermaidTheme } from "@/components/mermaid/useMermaidTheme";

export type MermaidVariant = "chat" | "document";

export interface MermaidDiagramProps {
  source: string;
  /** False while the fence is still streaming; nothing is rendered until true. */
  isComplete: boolean;
  variant: MermaidVariant;
  /** Shown as "Ask the agent to fix" on errors; hidden when absent. */
  onRequestFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
}

/** The raw keyword is used only for finished blocks, so partial keywords do not flicker. */
function typeLabel(
  t: TFunction,
  type: MermaidDiagramType,
  allowKeyword: boolean
): string {
  if (type.kind) {
    return t("mermaid.label", { type: t(`mermaid.types.${type.kind}`) });
  }
  if (allowKeyword && type.keyword) {
    return t("mermaid.label", { type: type.keyword });
  }
  return "mermaid";
}

export function MermaidDiagram({
  source,
  isComplete,
  variant,
  onRequestFix,
}: MermaidDiagramProps) {
  const { t } = useTranslation();
  const theme = useMermaidTheme();
  const state = useMermaidRender(source, isComplete, theme);
  const [scopeId] = useState(createSvgScopeId);
  const [view, setView] = useState<MermaidView>("diagram");
  const [viewerOpen, setViewerOpen] = useState(false);

  const shown = state.status === "rendered" ? state.result : state.lastGood;
  const svg = useMemo(
    () =>
      shown
        ? sanitizeMermaidSvg(rescopeSvgIds(shown.svg, shown.renderId, scopeId))
        : null,
    [shown, scopeId]
  );
  const diagramType = useMemo(() => detectDiagramType(source), [source]);
  const accessibleName = useMemo(
    () => (svg ? readSvgAccessibleName(svg) : null),
    [svg]
  );
  const label = typeLabel(t, diagramType, isComplete);
  const diagnostic = state.status === "error" ? state.diagnostic : null;
  const errorMessage = diagnostic
    ? describeMermaidDiagnostic(t, diagnostic)
    : null;
  const requestFix =
    onRequestFix && diagnostic
      ? () => onRequestFix(source, diagnostic)
      : undefined;

  const copySource = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(source);
      toast.success(t("mermaid.copied"));
    } catch {
      toast.error(t("mermaid.copyFailed"));
    }
  }, [source, t]);

  const downloadAsSvg = useCallback(() => {
    if (svg) downloadSvg(svg, mermaidFileName(diagramType.kind, "svg"));
  }, [svg, diagramType.kind]);

  const downloadAsPng = useCallback(async () => {
    if (!svg) return;
    const background = theme.themeVariables.background;
    try {
      const blob = await svgToPngBlob(
        svg,
        typeof background === "string"
          ? background
          : theme.darkMode
            ? "#000000"
            : "#ffffff"
      );
      downloadBlob(blob, mermaidFileName(diagramType.kind, "png"));
    } catch {
      toast.error(t("mermaid.downloadFailed"));
    }
  }, [svg, theme, diagramType.kind, t]);

  const onDownloadPngAction = useCallback(() => {
    void downloadAsPng();
  }, [downloadAsPng]);
  const onCopyAction = useCallback(() => {
    void copySource();
  }, [copySource]);
  const onExpandAction = useCallback(() => {
    setViewerOpen(true);
  }, []);

  const actions: MermaidToolbarActions | null = useMemo(
    () =>
      svg
        ? {
            view,
            onViewChange: setView,
            onCopy: onCopyAction,
            onDownloadSvg: downloadAsSvg,
            onDownloadPng: onDownloadPngAction,
            onExpand: onExpandAction,
          }
        : null,
    [
      svg,
      view,
      onCopyAction,
      downloadAsSvg,
      onDownloadPngAction,
      onExpandAction,
    ]
  );

  let body: ReactNode;
  if (svg && view === "diagram") {
    body = (
      <div
        role="img"
        aria-label={accessibleName ?? label}
        data-testid="mermaid-svg"
        className="flex justify-center overflow-x-auto p-3 [&_svg]:h-auto [&_svg]:max-w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  } else if (svg) {
    body = (
      <MermaidSource source={source} highlightLine={diagnostic?.line ?? null} />
    );
  } else if (diagnostic && errorMessage) {
    body = (
      <MermaidErrorView
        source={source}
        message={errorMessage}
        highlightLine={diagnostic.line}
        onCopy={onCopyAction}
        onRequestFix={requestFix}
      />
    );
  } else {
    body = <MermaidPending source={source} isComplete={isComplete} />;
  }

  return (
    <div
      data-testid="mermaid-diagram"
      data-variant={variant}
      data-status={state.status}
      className={cn(
        "not-prose my-3 min-w-0 overflow-hidden border border-border-01 bg-background-tint-00",
        variant === "chat" ? "rounded-12" : "rounded-08"
      )}
    >
      <MermaidToolbar
        label={label}
        showLabel={variant === "chat"}
        actions={actions}
      />
      {body}
      {svg && errorMessage && (
        <div
          data-testid="mermaid-stale"
          className="flex flex-wrap items-center gap-2 border-t border-border-01 px-3 py-1.5"
        >
          <Text secondaryBody className="text-status-error-05">
            {`${errorMessage} ${t("mermaid.staleNotice")}`}
          </Text>
          {requestFix && (
            <Button size="sm" prominence="secondary" onClick={requestFix}>
              {t("mermaid.askAgentToFix")}
            </Button>
          )}
        </div>
      )}
      {svg && viewerOpen && (
        <MermaidViewer
          open={viewerOpen}
          onOpenChange={setViewerOpen}
          title={label}
          svg={svg}
          svgScopeId={scopeId}
        />
      )}
    </div>
  );
}
