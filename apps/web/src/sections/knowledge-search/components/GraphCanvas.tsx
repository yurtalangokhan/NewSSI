"use client";

import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgExpand, SvgNetworkGraph, SvgZoomIn, SvgZoomOut } from "@opal/icons";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import Text from "@/refresh-components/texts/Text";
import EntityColorDot from "@/sections/knowledge-search/components/EntityColorDot";
import GraphDepthPopover from "@/sections/knowledge-search/components/GraphDepthPopover";
import GraphRelationList from "@/sections/knowledge-search/components/GraphRelationList";
import KnowledgeForceGraph, {
  type KnowledgeForceGraphHandle,
} from "@/refresh-components/knowledge-graph/KnowledgeForceGraph";
import { entityLabelCounts } from "@/sections/knowledge-search/model/graphModel";
import type { GraphDepth } from "@/sections/knowledge-search/model/searchState";
import type {
  KnowledgeGraph,
  KnowledgeGraphNode,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const CANVAS_HEIGHT = 560;
const ZOOM_STEP = 1.25;

interface GraphCanvasProps {
  graph: KnowledgeGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: KnowledgeGraphNode) => void;
  depth: GraphDepth;
  onDepthChange: (depth: GraphDepth) => void;
  matchedOnly: boolean;
  onMatchedOnlyToggle: () => void;
  isExpanding: boolean;
  /** Whether the user may read graph neighborhoods for depth expansion. */
  canExpand: boolean;
}

/** The result graph with zoom, depth, and a relation list. */
export default function GraphCanvas({
  graph,
  selectedNodeId,
  onSelectNode,
  depth,
  onDepthChange,
  matchedOnly,
  onMatchedOnlyToggle,
  isExpanding,
  canExpand,
}: GraphCanvasProps) {
  const { t } = useTranslation();
  const graphRef = useRef<KnowledgeForceGraphHandle>(null);
  const legend = useMemo(() => entityLabelCounts(graph), [graph]);

  if (graph.nodes.length === 0) {
    return (
      <EmptyMessage
        icon={SvgNetworkGraph}
        title={t("knowledgeSearch.graph.empty")}
      />
    );
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-3">
      <div className="relative overflow-hidden rounded-16 border border-border-01 bg-background-neutral-00">
        <div className="pointer-events-none absolute inset-x-2.5 top-2.5 z-[1] flex flex-wrap items-center gap-1.5">
          <div className="pointer-events-auto">
            <GraphDepthPopover
              depth={depth}
              onDepthChange={onDepthChange}
              disabled={!canExpand}
            />
          </div>
          <div className="pointer-events-auto">
            <Button
              variant="select"
              selected={matchedOnly}
              aria-pressed={matchedOnly}
              size="md"
              onClick={onMatchedOnlyToggle}
            >
              {t("knowledgeSearch.graph.matchedOnly")}
            </Button>
          </div>
          {isExpanding && (
            <Text
              as="span"
              role="status"
              secondaryBody
              text03
              className="pointer-events-auto"
            >
              {t("knowledgeSearch.graph.expanding")}
            </Text>
          )}
          <div className="flex-1" />
          <div className="pointer-events-auto flex items-center rounded-12 border border-border-01 bg-background-neutral-00 p-0.5">
            <Button
              icon={SvgZoomIn}
              prominence="tertiary"
              size="md"
              tooltip={t("knowledgeSearch.graph.zoomIn")}
              aria-label={t("knowledgeSearch.graph.zoomIn")}
              onClick={() => graphRef.current?.zoomBy(ZOOM_STEP)}
            />
            <Button
              icon={SvgZoomOut}
              prominence="tertiary"
              size="md"
              tooltip={t("knowledgeSearch.graph.zoomOut")}
              aria-label={t("knowledgeSearch.graph.zoomOut")}
              onClick={() => graphRef.current?.zoomBy(1 / ZOOM_STEP)}
            />
            <Button
              icon={SvgExpand}
              prominence="tertiary"
              size="md"
              tooltip={t("knowledgeSearch.graph.fit")}
              aria-label={t("knowledgeSearch.graph.fit")}
              onClick={() => graphRef.current?.fit()}
            />
          </div>
        </div>
        <div
          style={{
            backgroundImage:
              "radial-gradient(var(--border-01) 1px, transparent 1px)",
            backgroundSize: "18px 18px",
          }}
        >
          <KnowledgeForceGraph
            ref={graphRef}
            graph={graph}
            height={CANVAS_HEIGHT}
            selectedNodeId={selectedNodeId}
            onSelectNode={onSelectNode}
            ariaLabel={t("knowledgeSearch.graph.label")}
          />
        </div>
      </div>

      <div
        data-testid="knowledge-graph-legend"
        className="flex flex-wrap items-center gap-x-4 gap-y-1"
      >
        {legend.map(({ value }) => (
          <span key={value} className="flex items-center gap-1.5">
            <EntityColorDot label={value} />
            <Text as="span" secondaryBody text03>
              {value}
            </Text>
          </span>
        ))}
        <span className="flex-1" aria-hidden />
        <Text as="span" secondaryBody text02>
          {t("knowledgeSearch.graph.legendHint")}
        </Text>
      </div>

      <GraphRelationList
        graph={graph}
        selectedNodeId={selectedNodeId}
        onSelectNode={onSelectNode}
      />
    </div>
  );
}
