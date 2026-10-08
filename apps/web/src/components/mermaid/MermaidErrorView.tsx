"use client";

import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgAlertTriangle } from "@/icons";
import Text from "@/refresh-components/texts/Text";
import { MermaidSource } from "@/components/mermaid/MermaidSourceView";

interface MermaidErrorViewProps {
  source: string;
  /** Already localized (describeMermaidDiagnostic). */
  message: string;
  highlightLine: number | null;
  onCopy: () => void;
  /** "Ask the agent to fix" is shown only when provided. */
  onRequestFix?: () => void;
}

export function MermaidErrorView({
  source,
  message,
  highlightLine,
  onCopy,
  onRequestFix,
}: MermaidErrorViewProps) {
  const { t } = useTranslation();
  return (
    <div data-testid="mermaid-error" className="flex flex-col">
      <div
        role="alert"
        className="flex items-start gap-2 bg-status-error-01 px-3 py-2 text-status-error-05"
      >
        <SvgAlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
        <Text secondaryBody className="text-status-error-05">
          {message}
        </Text>
      </div>
      <MermaidSource source={source} highlightLine={highlightLine} />
      <div className="flex flex-wrap gap-2 border-t border-border-01 px-3 py-2">
        {onRequestFix && (
          <Button size="sm" prominence="secondary" onClick={onRequestFix}>
            {t("mermaid.askAgentToFix")}
          </Button>
        )}
        <Button size="sm" prominence="tertiary" onClick={onCopy}>
          {t("mermaid.copyCode")}
        </Button>
      </div>
    </div>
  );
}
