import { useEffect, useImperativeHandle, type Ref } from "react";
import type { KnowledgeForceGraphHandle } from "@/refresh-components/knowledge-graph/KnowledgeForceGraph";
import type {
  SourceGraph,
  SourceGraphNode,
} from "@/lib/knowledge-graph/forceGraphModel";

/** The camera handle the stub exposes, for asserting toolbar calls. */
export const stubCamera = { zoomBy: jest.fn(), fit: jest.fn() };

/**
 * How many times an interactive stub mounted (previews are not counted), for
 * asserting the explorable graph is not remounted.
 */
export const stubLifecycle = { mounts: 0 };

/**
 * jsdom cannot draw on canvas: stands in for KnowledgeForceGraph with its nodes
 * as buttons named like the real node tooltips.
 * Use as `jest.mock(<KnowledgeForceGraph path>, () => jest.requireActual(<this>))`.
 */
export default function KnowledgeForceGraphStub({
  graph,
  onSelectNode,
  interactive = true,
  ariaLabel,
  ref,
}: {
  graph: SourceGraph;
  onSelectNode?: (node: SourceGraphNode) => void;
  interactive?: boolean;
  ariaLabel: string;
  ref?: Ref<KnowledgeForceGraphHandle>;
}) {
  useImperativeHandle(ref, () => stubCamera, []);
  useEffect(() => {
    if (interactive) stubLifecycle.mounts += 1;
  }, [interactive]);
  return (
    <div>
      <div role="img" aria-label={ariaLabel} />
      {interactive &&
        graph.nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            aria-label={`${node.name}, ${node.label}`}
            onClick={() => onSelectNode?.(node)}
          />
        ))}
    </div>
  );
}
