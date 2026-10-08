import type { TFunction } from "i18next";
import type { IconProps } from "@opal/types";
import { SvgNetworkGraph, SvgRefreshCw, SvgServer } from "@opal/icons";
import type { KnowledgeSearchSource } from "@/lib/api/domains/knowledge/knowledge-search-types";

const UNSYNCED_STATUSES = new Set(["failed", "error"]);

export interface SourcePresentation {
  icon: React.FunctionComponent<IconProps>;
  /** Tinted background and icon stroke classes. */
  tone: string;
  labelKey: string;
}

/** How a searchable source is shown: graph, connector, or documents. */
export function sourcePresentation(
  source: KnowledgeSearchSource | undefined
): SourcePresentation {
  if (source?.hasGraph) {
    return {
      icon: SvgNetworkGraph,
      tone: "bg-theme-purple-01 stroke-theme-purple-05",
      labelKey: "knowledgeSearch.rail.sourceType.graph",
    };
  }
  if (source?.sourceType === "connector") {
    return {
      icon: SvgRefreshCw,
      tone: "bg-theme-green-01 stroke-theme-green-05",
      labelKey: "knowledgeSearch.rail.sourceType.connector",
    };
  }
  return {
    icon: SvgServer,
    tone: "bg-theme-blue-01 stroke-theme-blue-05",
    labelKey: "knowledgeSearch.rail.sourceType.document",
  };
}

/** The source type, plus "synced" for healthy connectors. */
export function sourceSubtitle(
  source: KnowledgeSearchSource | undefined,
  t: TFunction
): string {
  const kind = t(sourcePresentation(source).labelKey);
  if (
    source?.sourceType === "connector" &&
    !UNSYNCED_STATUSES.has(source.syncStatus)
  ) {
    return `${kind} · ${t("knowledgeSearch.rail.synced")}`;
  }
  return kind;
}
