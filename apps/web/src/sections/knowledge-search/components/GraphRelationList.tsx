"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { SvgArrowRight } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import EntityColorDot from "@/sections/knowledge-search/components/EntityColorDot";
import type {
  KnowledgeGraph,
  KnowledgeGraphNode,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const MAX_LISTED_RELATIONS = 8;

interface GraphRelationListProps {
  graph: KnowledgeGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: KnowledgeGraphNode) => void;
}

/** The graph's relationships as a list; a row selects its source entity. */
export default function GraphRelationList({
  graph,
  selectedNodeId,
  onSelectNode,
}: GraphRelationListProps) {
  const { t } = useTranslation();
  const nodesById = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph]
  );
  if (graph.edges.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-16 border border-border-01 bg-background-neutral-00">
      <div className="flex items-center justify-between border-b border-border-01 px-3.5 py-2.5">
        <Text as="h3" mainUiAction text05>
          {t("knowledgeSearch.graph.relations")}
        </Text>
        <Text as="span" secondaryMono text02>
          {graph.edges.length}
        </Text>
      </div>
      <ul
        aria-label={t("knowledgeSearch.graph.relations")}
        className="flex flex-col"
      >
        {graph.edges.slice(0, MAX_LISTED_RELATIONS).map((edge, index) => {
          const source = nodesById.get(edge.source);
          const target = nodesById.get(edge.target);
          if (!source || !target) return null;
          return (
            <li
              key={edge.id ?? `${edge.source}-${edge.type}-${index}`}
              className="border-b border-border-01 last:border-b-0"
            >
              <Interactive.Base
                variant="select"
                prominence="light"
                selected={source.id === selectedNodeId}
                onClick={() => onSelectNode(source)}
              >
                <Interactive.Container
                  type="button"
                  heightVariant="fit"
                  widthVariant="full"
                  roundingVariant="mini"
                >
                  <span className="flex w-full flex-wrap items-center gap-2 px-3.5 py-2 text-left">
                    <EntityColorDot label={source.label} />
                    <Text as="span" secondaryBody text04>
                      {source.name}
                    </Text>
                    <Text as="span" secondaryMono text03>
                      {edge.type}
                    </Text>
                    <SvgArrowRight className="h-3 w-3 stroke-text-02" />
                    <EntityColorDot label={target.label} />
                    <Text as="span" secondaryBody text04>
                      {target.name}
                    </Text>
                  </span>
                </Interactive.Container>
              </Interactive.Base>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
