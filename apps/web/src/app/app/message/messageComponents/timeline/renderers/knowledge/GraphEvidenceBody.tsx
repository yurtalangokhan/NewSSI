import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import KnowledgeForceGraph from "@/refresh-components/knowledge-graph/KnowledgeForceGraph";
import type {
  EvidenceGraph,
  KnowledgeEvidence,
} from "@/lib/api/domains/chat/knowledge-evidence-types";
import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";
import { rankedMatches } from "@/lib/knowledge-graph/forceGraphModel";
import { EvidenceEntityDetails } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceEntityDetails";
import { EvidenceQueryLine } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceQueryLine";
import { EvidenceRelationList } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceRelationList";
import { EvidenceTopMatches } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/EvidenceTopMatches";
import {
  focusedNodeId,
  GraphSelection,
  highlightFor,
  relationCount,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/graphSelection";
import { ModelContextDisclosure } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/ModelContextDisclosure";

type GraphMode = "graph" | "list";

const EMPTY_GRAPH: EvidenceGraph = { nodes: [], edges: [] };
const GRAPH_HEIGHT = 340;
const COMPACT_GRAPH_HEIGHT = 260;
// Same quiet dots as the knowledge search page's graph canvas.
const DOT_GRID = {
  backgroundImage: "radial-gradient(var(--border-01) 1px, transparent 1px)",
  backgroundSize: "18px 18px",
};

interface GraphEvidenceBodyProps {
  evidence: KnowledgeEvidence;
  /** Narrow surfaces stack the ranking above the details. */
  compact?: boolean;
}

/**
 * What a graph search found: the matched entities drawn with their
 * neighborhood, ranked by strength, and the details of one of them.
 */
export function GraphEvidenceBody({
  evidence,
  compact = false,
}: GraphEvidenceBodyProps) {
  const { t } = useTranslation();
  const graph = evidence.graph ?? EMPTY_GRAPH;
  const [mode, setMode] = useState<GraphMode>("graph");
  // Nothing is picked at first, so the drawing opens undimmed; the details
  // still show the strongest match.
  const [selection, setSelection] = useState<GraphSelection>(null);
  const highlight = useMemo(
    () => highlightFor(graph, selection),
    [graph, selection]
  );
  const matches = useMemo(() => rankedMatches(graph.nodes), [graph.nodes]);
  const pickedId = focusedNodeId(graph, selection);
  const focusedId = pickedId ?? matches[0]?.id ?? graph.nodes[0]?.id ?? null;
  const focused = graph.nodes.find((node) => node.id === focusedId) ?? null;
  const focusedRelationCount = focused ? relationCount(graph, focused.id) : 0;
  const labels = useMemo(
    () => Array.from(new Set(graph.nodes.map((node) => node.label))),
    [graph.nodes]
  );
  const graphHeight = compact ? COMPACT_GRAPH_HEIGHT : GRAPH_HEIGHT;
  const selectNode = (id: string) => setSelection({ kind: "node", id });

  if (graph.nodes.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <EvidenceQueryLine evidence={evidence} />
        <Text as="p" secondaryBody text03>
          {t("knowledgeCard.noResults")}
        </Text>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <EvidenceQueryLine evidence={evidence} />

      <div className="relative overflow-hidden rounded-08 border border-border-01 bg-background-tint-01">
        <div
          className="absolute left-2 top-2 z-[1] flex gap-1"
          role="group"
          aria-label={t("knowledgeCard.viewLabel")}
        >
          <Button
            variant="select"
            size="sm"
            selected={mode === "graph"}
            aria-pressed={mode === "graph"}
            onClick={() => setMode("graph")}
          >
            {t("knowledgeCard.graphView")}
          </Button>
          <Button
            variant="select"
            size="sm"
            selected={mode === "list"}
            aria-pressed={mode === "list"}
            onClick={() => setMode("list")}
          >
            {t("knowledgeCard.listView")}
          </Button>
        </div>

        {mode === "graph" ? (
          <div style={DOT_GRID}>
            <KnowledgeForceGraph
              graph={graph}
              height={graphHeight}
              selectedNodeId={pickedId}
              onSelectNode={(node) => selectNode(node.id)}
              ariaLabel={t("knowledgeCard.graphLabel")}
            />
          </div>
        ) : (
          <div
            className="overflow-y-auto px-2 pb-2 pt-11"
            style={{ maxHeight: graphHeight }}
          >
            <EvidenceRelationList
              graph={graph}
              highlight={highlight}
              onSelect={setSelection}
              ariaLabel={t("knowledgeCard.allRelations")}
            />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border-01 bg-background-neutral-00 px-3 py-2">
          <LegendItem
            swatch={<span className="h-2.5 w-2.5 rounded-full bg-text-04" />}
            text={t("knowledgeCard.legendMatched")}
          />
          <LegendItem
            swatch={
              <span className="h-2.5 w-2.5 rounded-full border-[1.5px] border-text-03" />
            }
            text={t("knowledgeCard.legendExpanded")}
          />
          <LegendItem
            swatch={
              <span
                className="h-2.5 w-2.5 rounded-full bg-text-04"
                style={{ boxShadow: "0 0 6px 2px var(--text-02)" }}
              />
            }
            text={t("knowledgeCard.legendGlow")}
          />
          <span aria-hidden className="h-3 w-px bg-border-02" />
          {labels.map((label) => (
            <LegendItem
              key={label}
              swatch={
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{
                    background: entityColorVar(entityColor(label), "05"),
                  }}
                />
              }
              text={label}
            />
          ))}
        </div>
      </div>

      {focused && (
        <div
          className={cn(
            "grid items-start gap-3",
            !compact && matches.length > 0 && "md:grid-cols-2"
          )}
        >
          {matches.length > 0 && (
            <EvidenceTopMatches
              matches={matches}
              focusedId={focusedId}
              onSelect={selectNode}
            />
          )}
          <EvidenceEntityDetails graph={graph} node={focused}>
            {focusedRelationCount > 0 && (
              <div className="flex flex-col gap-1 border-t border-border-01 pt-2">
                <Text as="p" secondaryAction text04>
                  {t("knowledgeCard.relations")} · {focusedRelationCount}
                </Text>
                <div className="max-h-48 overflow-y-auto">
                  <EvidenceRelationList
                    graph={graph}
                    highlight={highlight}
                    onSelect={setSelection}
                    ariaLabel={t("knowledgeCard.relations")}
                    nodeId={focused.id}
                  />
                </div>
              </div>
            )}
          </EvidenceEntityDetails>
        </div>
      )}

      {!compact && (
        <ModelContextDisclosure
          context={evidence.modelContext}
          truncated={evidence.modelContextTruncated}
        />
      )}
    </div>
  );
}

interface LegendItemProps {
  swatch: ReactNode;
  text: string;
}

function LegendItem({ swatch, text }: LegendItemProps) {
  return (
    <span className="flex items-center gap-1.5">
      <span aria-hidden className="flex">
        {swatch}
      </span>
      <Text as="span" secondaryBody text03>
        {text}
      </Text>
    </span>
  );
}
