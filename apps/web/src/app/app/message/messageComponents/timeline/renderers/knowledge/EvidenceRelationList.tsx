import { Interactive } from "@opal/core";
import Text from "@/refresh-components/texts/Text";
import type { EvidenceGraph } from "@/lib/api/domains/chat/knowledge-evidence-types";
import {
  GraphSelection,
  Highlight,
  keyedEdges,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/graphSelection";

interface EvidenceRelationListProps {
  graph: EvidenceGraph;
  highlight: Highlight | null;
  onSelect: (selection: GraphSelection) => void;
  ariaLabel: string;
  /** Only the relations touching this entity; every relation when absent. */
  nodeId?: string | null;
}

/** Relations as "source TYPE → target"; picking one highlights it. */
export function EvidenceRelationList({
  graph,
  highlight,
  onSelect,
  ariaLabel,
  nodeId = null,
}: EvidenceRelationListProps) {
  const names = new Map(graph.nodes.map((node) => [node.id, node.name]));
  const rows = keyedEdges(graph, nodeId);

  return (
    <ul aria-label={ariaLabel} className="flex flex-col gap-0.5">
      {rows.map(({ edge, key }) => {
        const pressed = highlight?.edges.has(key) ?? false;
        return (
          <li key={key}>
            <Interactive.Base
              variant="select"
              prominence="heavy"
              selected={pressed}
              onClick={() => onSelect({ kind: "edge", key })}
            >
              <Interactive.Container
                type="button"
                aria-pressed={pressed}
                heightVariant="fit"
                widthVariant="full"
                roundingVariant="compact"
              >
                <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 px-2 py-1.5 text-left">
                  <Text as="span" secondaryBody text05>
                    {names.get(edge.source)}
                  </Text>
                  <Text
                    as="span"
                    secondaryMono
                    text03
                    className="rounded-04 border border-border-02 px-1"
                  >
                    {edge.type}
                  </Text>
                  <Text as="span" secondaryBody text02 aria-hidden>
                    →
                  </Text>
                  <Text as="span" secondaryBody text05>
                    {names.get(edge.target)}
                  </Text>
                </span>
              </Interactive.Container>
            </Interactive.Base>
          </li>
        );
      })}
    </ul>
  );
}
