"use client";

import CardSection from "@/components/admin/CardSection";
import Text from "@/refresh-components/texts/Text";
import { SvgX, SvgChevronRight } from "@opal/icons";
import type { GraphNode, GraphEdge } from "@/lib/langconnect";
import { useTranslation } from "react-i18next";

const ISO_DATE_RE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

function formatPropertyValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  const str = String(value);
  if (ISO_DATE_RE.test(str)) {
    const d = new Date(str);
    if (!isNaN(d.getTime())) {
      return d.toLocaleString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    }
  }
  return str;
}

interface EntityPreviewProps {
  node: GraphNode | null;
  edges: GraphEdge[];
  nodes: GraphNode[];
  onClose: () => void;
  onNodeSelect?: (node: GraphNode) => void;
}

export default function EntityPreview({
  node,
  edges,
  nodes,
  onClose,
  onNodeSelect,
}: EntityPreviewProps) {
  const { t } = useTranslation();
  if (!node) return null;

  const outgoing = edges.filter((e) => e.source === node.id);
  const incoming = edges.filter((e) => e.target === node.id);
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const propEntries = node.properties ? Object.entries(node.properties) : [];

  return (
    <CardSection className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Text
            as="p"
            mainUiAction
            text04
            className="text-sm font-semibold truncate"
          >
            {node.name}
          </Text>
          <span className="inline-flex shrink-0 items-center rounded-full border border-theme-primary-03 bg-theme-primary-01 px-2 py-0.5 text-[11px] text-theme-primary-07 font-medium">
            {node.label}
          </span>
          <Text
            as="span"
            mainContentMuted
            text03
            className="text-xs shrink-0 hidden sm:inline"
          >
            ID: {node.id.slice(0, 12)}…
          </Text>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-04 p-1 hover:bg-background-neutral-01 transition-colors"
          aria-label={t("entityPreview.closeAriaLabel")}
        >
          <SvgX className="h-4 w-4 stroke-text-03" />
        </button>
      </div>

      {/* 3-column grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {/* Properties */}
        <div className="flex flex-col gap-1.5">
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium uppercase tracking-wide"
          >
            {t("entityPreview.properties", { count: propEntries.length })}
          </Text>
          {propEntries.length === 0 ? (
            <Text as="p" mainContentMuted text03 className="text-xs">
              {t("entityPreview.noProperties")}
            </Text>
          ) : (
            <div className="max-h-44 overflow-y-auto flex flex-col gap-0.5 pr-1">
              {propEntries.map(([key, value]) => (
                <div
                  key={key}
                  className="grid grid-cols-[90px_1fr] gap-1 rounded-04 px-2 py-1 text-xs even:bg-background-neutral-01"
                >
                  <span className="font-medium text-text-03 truncate">
                    {key}
                  </span>
                  <span className="break-words text-text-04">
                    {formatPropertyValue(value)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Outgoing */}
        <div className="flex flex-col gap-1.5">
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium uppercase tracking-wide"
          >
            {t("entityPreview.outgoing", { count: outgoing.length })}
          </Text>
          {outgoing.length === 0 ? (
            <Text as="p" mainContentMuted text03 className="text-xs">
              {t("entityPreview.noOutgoing")}
            </Text>
          ) : (
            <div className="max-h-44 overflow-y-auto flex flex-col gap-1 pr-1">
              {outgoing.map((edge, i) => {
                const target = nodeMap.get(edge.target);
                return (
                  <button
                    key={i}
                    onClick={() => target && onNodeSelect?.(target)}
                    className="flex items-center gap-2 rounded-08 border border-border-01 px-2 py-1.5 text-xs hover:bg-background-neutral-01 transition-colors text-left"
                  >
                    <span className="inline-flex shrink-0 items-center rounded border border-border-01 bg-background-tint-00 px-1.5 py-0.5 text-[10px] text-text-03">
                      {edge.type}
                    </span>
                    <SvgChevronRight className="h-3 w-3 stroke-text-03 shrink-0" />
                    <span className="font-medium text-text-04 truncate">
                      {target?.name ?? edge.target.slice(0, 12)}
                    </span>
                    {target && (
                      <span className="ml-auto shrink-0 inline-flex items-center rounded-full bg-background-neutral-01 px-1.5 py-0.5 text-[10px] text-text-03 border border-border-01">
                        {target.label}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Incoming */}
        <div className="flex flex-col gap-1.5">
          <Text
            as="p"
            mainContentMuted
            text03
            className="text-xs font-medium uppercase tracking-wide"
          >
            {t("entityPreview.incoming", { count: incoming.length })}
          </Text>
          {incoming.length === 0 ? (
            <Text as="p" mainContentMuted text03 className="text-xs">
              {t("entityPreview.noIncoming")}
            </Text>
          ) : (
            <div className="max-h-44 overflow-y-auto flex flex-col gap-1 pr-1">
              {incoming.map((edge, i) => {
                const source = nodeMap.get(edge.source);
                return (
                  <button
                    key={i}
                    onClick={() => source && onNodeSelect?.(source)}
                    className="flex items-center gap-2 rounded-08 border border-border-01 px-2 py-1.5 text-xs hover:bg-background-neutral-01 transition-colors text-left"
                  >
                    <span className="font-medium text-text-04 truncate">
                      {source?.name ?? edge.source.slice(0, 12)}
                    </span>
                    <SvgChevronRight className="h-3 w-3 stroke-text-03 shrink-0" />
                    <span className="inline-flex shrink-0 items-center rounded border border-border-01 bg-background-tint-00 px-1.5 py-0.5 text-[10px] text-text-03">
                      {edge.type}
                    </span>
                    {source && (
                      <span className="ml-auto shrink-0 inline-flex items-center rounded-full bg-background-neutral-01 px-1.5 py-0.5 text-[10px] text-text-03 border border-border-01">
                        {source.label}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </CardSection>
  );
}
