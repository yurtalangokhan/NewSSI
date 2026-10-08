import { useEffect, useMemo } from "react";
import { SvgFileText, SvgNetworkGraph } from "@opal/icons";
import {
  CustomToolPacket,
  PacketType,
} from "@/lib/api/domains/chat/streaming-types";
import {
  MessageRenderer,
  RenderType,
  RendererResult,
} from "@/app/app/message/messageComponents/interfaces";
import { KnowledgeCallBody } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeCallBody";
import { KnowledgeCallHeader } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeCallHeader";
import {
  constructKnowledgeCalls,
  isGraphCall,
  KnowledgeCall,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/knowledgeCalls";

function resultFor(
  call: KnowledgeCall,
  renderType: RenderType
): RendererResult {
  const icon = isGraphCall(call) ? SvgNetworkGraph : SvgFileText;
  const header = <KnowledgeCallHeader call={call} />;

  if (renderType === RenderType.HIGHLIGHT || renderType === RenderType.INLINE) {
    return {
      icon: null,
      status: null,
      supportsCollapsible: true,
      timelineLayout: "content",
      content: header,
    };
  }
  return {
    icon,
    status: header,
    supportsCollapsible: true,
    timelineLayout: "timeline",
    content:
      renderType === RenderType.COMPACT ? (
        <></>
      ) : (
        <KnowledgeCallBody call={call} />
      ),
  };
}

/**
 * `database_search` / `graph_search` calls (and flow retrieval steps) as
 * evidence cards: the chunks or the subgraph the model was given, one
 * timeline step per call.
 */
export const KnowledgeRetrievalRenderer: MessageRenderer<
  CustomToolPacket,
  {}
> = ({ packets, onComplete, renderType, children }) => {
  const calls = useMemo(() => constructKnowledgeCalls(packets), [packets]);
  const sectionEnded = packets.some(
    (packet) =>
      packet.obj.type === PacketType.SECTION_END ||
      packet.obj.type === PacketType.ERROR
  );
  const isComplete =
    calls.length > 0 &&
    (sectionEnded || calls.every((call) => call.status !== "running"));

  useEffect(() => {
    if (isComplete) onComplete();
  }, [isComplete, onComplete]);

  return children(calls.map((call) => resultFor(call, renderType)));
};

export default KnowledgeRetrievalRenderer;
