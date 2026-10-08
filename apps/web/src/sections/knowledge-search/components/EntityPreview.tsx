"use client";

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { Button, Tag } from "@opal/components";
import { SvgNetworkGraph, SvgServer } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import EntityDot from "@/sections/knowledge-search/components/EntityDot";
import EntityLabelBadge from "@/sections/knowledge-search/components/EntityLabelBadge";
import KnowledgeGraphSvg from "@/sections/knowledge-search/components/KnowledgeGraphSvg";
import RelevanceMeter from "@/sections/knowledge-search/components/RelevanceMeter";
import KeyValueList from "@/sections/knowledge-search/components/KeyValueList";
import LabeledSection from "@/sections/knowledge-search/components/LabeledSection";
import PreviewBody from "@/sections/knowledge-search/components/PreviewBody";
import PreviewHeader from "@/sections/knowledge-search/components/PreviewHeader";
import { egoGraph } from "@/sections/knowledge-search/model/documentChunks";
import {
  MAX_NODE_EXPANSION_DEPTH,
  relationsOf,
} from "@/sections/knowledge-search/model/graphModel";
import type {
  KnowledgeGraph,
  KnowledgeGraphNode,
  KnowledgeSearchHit,
} from "@/lib/api/domains/knowledge/knowledge-search-types";

const EGO_GRAPH = { width: 560, height: 360 };

interface EntityPreviewProps {
  node: KnowledgeGraphNode;
  /** The result card behind the node, when it is a search hit. */
  hit?: KnowledgeSearchHit;
  graph: KnowledgeGraph;
  collectionName: string;
  onExpand: (node: KnowledgeGraphNode) => void;
  isExpanding: boolean;
  /** Hops of neighbors already loaded around the node. */
  expansionDepth: number;
  /** Whether the user may read graph neighborhoods. */
  canExpand: boolean;
  onSelectNode: (node: KnowledgeGraphNode) => void;
  onClose: () => void;
}

/** A graph entity with its neighborhood, relationships, and properties. */
export default function EntityPreview({
  node,
  hit,
  graph,
  collectionName,
  onExpand,
  isExpanding,
  expansionDepth,
  canExpand,
  onSelectNode,
  onClose,
}: EntityPreviewProps) {
  const { t } = useTranslation();
  const ego = useMemo(() => egoGraph(graph, node.id), [graph, node.id]);
  const relations = useMemo(
    () => relationsOf(graph, node.id),
    [graph, node.id]
  );
  const fullyExpanded = expansionDepth >= MAX_NODE_EXPANSION_DEPTH;
  const relationsTitle = t("knowledgeSearch.preview.relations", {
    count: relations.length,
  });

  return (
    <>
      <PreviewHeader
        marker={<EntityDot label={node.label} matched={node.matched} />}
        title={node.name}
        onClose={onClose}
        tags={
          <>
            <EntityLabelBadge label={node.label} />
            {node.matched ? (
              <Tag title={t("knowledgeSearch.hit.matched")} color="green" />
            ) : (
              <Tag title={t("knowledgeSearch.hit.neighbor")} />
            )}
            <Tag icon={SvgServer} title={collectionName} />
            {hit && <RelevanceMeter value={hit.relevance} />}
          </>
        }
        actions={
          <>
            <Button
              icon={SvgNetworkGraph}
              prominence="primary"
              disabled={isExpanding || !canExpand || fullyExpanded}
              tooltip={
                canExpand ? undefined : t("knowledgeSearch.graph.noPermission")
              }
              onClick={() => onExpand(node)}
            >
              {isExpanding
                ? t("knowledgeSearch.preview.expanding")
                : fullyExpanded
                  ? t("knowledgeSearch.preview.expandedAll")
                  : t(
                      expansionDepth === 0
                        ? "knowledgeSearch.preview.expand"
                        : "knowledgeSearch.preview.expandDeeper"
                    )}
            </Button>
          </>
        }
      />
      <PreviewBody>
        {ego.nodes.length > 1 && (
          <LabeledSection title={t("knowledgeSearch.preview.neighborhood")}>
            <div className="rounded-16 border border-border-01 bg-background-neutral-00 p-2">
              <KnowledgeGraphSvg
                graph={ego}
                width={EGO_GRAPH.width}
                height={EGO_GRAPH.height}
                labels="all"
                labelSize={15}
                selectedNodeId={node.id}
                onSelectNode={onSelectNode}
                ariaLabel={t("knowledgeSearch.preview.neighborhood")}
              />
            </div>
          </LabeledSection>
        )}

        <LabeledSection title={relationsTitle}>
          {relations.length === 0 ? (
            <Text as="p" secondaryBody text03>
              {t("knowledgeSearch.preview.noRelations")}
            </Text>
          ) : (
            <ul
              aria-label={relationsTitle}
              className="flex flex-col overflow-hidden rounded-12 border border-border-01"
            >
              {relations.map((relation) => (
                <li
                  key={`${relation.direction}-${relation.type}-${relation.other.id}`}
                  className="border-b border-border-01 last:border-b-0"
                >
                  <Interactive.Base
                    variant="select"
                    prominence="light"
                    onClick={() => onSelectNode(relation.other)}
                  >
                    <Interactive.Container
                      type="button"
                      heightVariant="fit"
                      widthVariant="full"
                      roundingVariant="mini"
                    >
                      <span className="flex w-full items-center gap-2 px-3 py-2 text-left">
                        <Text as="span" secondaryMono text03>
                          {relation.direction === "out"
                            ? `${relation.type} →`
                            : `← ${relation.type}`}
                        </Text>
                        <EntityDot
                          label={relation.other.label}
                          matched={relation.other.matched}
                        />
                        <Text
                          as="span"
                          secondaryBody
                          text04
                          className="min-w-0 truncate"
                        >
                          {relation.other.name}
                        </Text>
                      </span>
                    </Interactive.Container>
                  </Interactive.Base>
                </li>
              ))}
            </ul>
          )}
        </LabeledSection>

        {Object.keys(node.properties).length > 0 && (
          <LabeledSection title={t("knowledgeSearch.preview.properties")}>
            <KeyValueList entries={node.properties} />
          </LabeledSection>
        )}
      </PreviewBody>
    </>
  );
}
