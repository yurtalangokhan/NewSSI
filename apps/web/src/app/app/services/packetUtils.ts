import {
  FetchToolDocuments,
  MessageDelta,
  MessageStart,
  PacketType,
  SearchToolDocumentsDelta,
  StreamingCitation,
} from "./streamingModels";
import { Packet } from "@/app/app/services/streamingModels";
import { OnyxDocument } from "@/lib/search/interfaces";

export function isToolPacket(
  packet: Packet,
  includeSectionEnd: boolean = true
) {
  let toolPacketTypes = [
    PacketType.SEARCH_TOOL_START,
    PacketType.SEARCH_TOOL_QUERIES_DELTA,
    PacketType.SEARCH_TOOL_DOCUMENTS_DELTA,
    PacketType.PYTHON_TOOL_START,
    PacketType.PYTHON_TOOL_DELTA,
    PacketType.CUSTOM_TOOL_START,
    PacketType.CUSTOM_TOOL_DELTA,
    PacketType.FILE_READER_START,
    PacketType.FILE_READER_RESULT,
    PacketType.REASONING_START,
    PacketType.REASONING_DELTA,
    PacketType.FETCH_TOOL_START,
    PacketType.FETCH_TOOL_URLS,
    PacketType.FETCH_TOOL_DOCUMENTS,
    PacketType.MEMORY_TOOL_START,
    PacketType.MEMORY_TOOL_DELTA,
    PacketType.MEMORY_TOOL_NO_ACCESS,
    PacketType.LONG_TERM_MEMORY_RECALL,
    PacketType.LONG_TERM_MEMORY_SAVE,
    PacketType.DEEP_RESEARCH_PLAN_START,
    PacketType.DEEP_RESEARCH_PLAN_DELTA,
    PacketType.RESEARCH_AGENT_START,
    PacketType.INTERMEDIATE_REPORT_START,
    PacketType.INTERMEDIATE_REPORT_DELTA,
    PacketType.INTERMEDIATE_REPORT_CITED_DOCS,
  ];
  if (includeSectionEnd) {
    toolPacketTypes.push(PacketType.SECTION_END);
    toolPacketTypes.push(PacketType.ERROR);
  }
  return toolPacketTypes.includes(packet.obj.type as PacketType);
}

// Check if a packet is an actual tool call (not reasoning/thinking).
// This is used to determine if we should reset finalAnswerComing state
// when a tool packet arrives after message packets (Claude workaround).
// Reasoning packets should NOT reset finalAnswerComing since they are
// just the model thinking, not actual tool calls that would produce new content.
export function isActualToolCallPacket(packet: Packet): boolean {
  return (
    isToolPacket(packet, false) &&
    packet.obj.type !== PacketType.REASONING_START &&
    packet.obj.type !== PacketType.REASONING_DELTA
  );
}

export function isDisplayPacket(packet: Packet) {
  // Include MESSAGE_DELTA so tokens without MESSAGE_START still get displayed
  return (
    packet.obj.type === PacketType.MESSAGE_START ||
    packet.obj.type === PacketType.MESSAGE_DELTA ||
    packet.obj.type === PacketType.IMAGE_GENERATION_TOOL_START ||
    packet.obj.type === PacketType.GENERATED_FILE ||
    // The generation skeleton renders in the same slot the file card will
    // occupy, so its group must be classified as display. Every lifecycle
    // packet counts: a group is classified by whichever arrives first, and a
    // model that writes its whole tool call inside a reasoning block produces
    // no `start` until the tool is already rendering.
    packet.obj.type === PacketType.DOCUMENT_GENERATION_START ||
    packet.obj.type === PacketType.DOCUMENT_GENERATION_PROGRESS ||
    packet.obj.type === PacketType.DOCUMENT_GENERATION_END
  );
}

export function isSearchToolPacket(packet: Packet): boolean {
  return (
    packet.obj.type === PacketType.SEARCH_TOOL_START ||
    packet.obj.type === PacketType.SEARCH_TOOL_QUERIES_DELTA ||
    packet.obj.type === PacketType.SEARCH_TOOL_DOCUMENTS_DELTA
  );
}

export function isStreamingComplete(packets: Packet[]) {
  return packets.some((packet) => packet.obj.type === PacketType.STOP);
}

export function isFinalAnswerComing(packets: Packet[]) {
  return packets.some(
    (packet) =>
      packet.obj.type === PacketType.MESSAGE_START ||
      packet.obj.type === PacketType.IMAGE_GENERATION_TOOL_START
  );
}

export function isFinalAnswerComplete(packets: Packet[]) {
  // Find the first MESSAGE_START packet and get its index
  const messageStartPacket = packets.find(
    (packet) =>
      packet.obj.type === PacketType.MESSAGE_START ||
      packet.obj.type === PacketType.IMAGE_GENERATION_TOOL_START
  );

  if (!messageStartPacket) {
    // No MESSAGE_START yet - check if we have MESSAGE_DELTA packets indicating content is coming
    // This handles the case where backend sends tokens directly without MESSAGE_START
    const hasMessageDelta = packets.some(
      (packet) => packet.obj.type === PacketType.MESSAGE_DELTA
    );
    if (hasMessageDelta) {
      console.log(
        "[isFinalAnswerComplete] No MESSAGE_START but has MESSAGE_DELTA, returning true"
      );
      return true;
    }
    console.log(
      "[isFinalAnswerComplete] No MESSAGE_START found, returning false"
    );
    return false;
  }

  // Check if there's a corresponding SECTION_END, ERROR, or STOP with the same turn_index
  // STOP packets indicate the stream has completed
  const hasStop = packets.some(
    (packet) =>
      (packet.obj.type === PacketType.SECTION_END ||
        packet.obj.type === PacketType.ERROR ||
        packet.obj.type === PacketType.STOP) &&
      packet.placement.turn_index === messageStartPacket.placement.turn_index
  );

  if (hasStop) {
    console.log("[isFinalAnswerComplete] hasStop found, returning true");
    return true;
  }

  // No SECTION_END/ERROR/STOP yet - check if we have MESSAGE_DELTA packets indicating content is streaming
  // This handles the case where backend sends MESSAGE_START + MESSAGE_DELTA without SECTION_END/STOP
  const hasMessageDelta = packets.some(
    (packet) =>
      packet.obj.type === PacketType.MESSAGE_DELTA &&
      packet.placement.turn_index === messageStartPacket.placement.turn_index
  );

  if (hasMessageDelta) {
    console.log("[isFinalAnswerComplete] has MESSAGE_DELTA, returning true");
    return true;
  }

  console.log(
    "[isFinalAnswerComplete] No stop packet or delta found, returning false"
  );
  return false;
}

export function groupPacketsByTurnIndex(
  packets: Packet[]
): { turn_index: number; tab_index: number; packets: Packet[] }[] {
  /*
  Group packets by (turn_index, tab_index). 
  Ordered from lowest turn_index to highest, then by tab_index within each turn.
  This supports parallel tool calls where multiple tools share the same turn_index
  but have different tab_index values.
  */
  const groups = packets.reduce(
    (
      acc: Map<
        string,
        { turn_index: number; tab_index: number; packets: Packet[] }
      >,
      packet
    ) => {
      const turn_index = packet.placement.turn_index;
      const tab_index = packet.placement.tab_index ?? 0;
      const key = `${turn_index}-${tab_index}`;
      if (!acc.has(key)) {
        acc.set(key, { turn_index, tab_index, packets: [] });
      }
      acc.get(key)!.packets.push(packet);
      return acc;
    },
    new Map()
  );

  // Convert to array and sort by turn_index first, then tab_index
  return Array.from(groups.values()).sort((a, b) => {
    if (a.turn_index !== b.turn_index) {
      return a.turn_index - b.turn_index;
    }
    return a.tab_index - b.tab_index;
  });
}

export function getTextContent(packets: Packet[]) {
  // Prefer MESSAGE_DELTA tokens when present (streaming); fall back to MESSAGE_START
  // content only for historical messages that have no delta packets.
  const hasDelta = packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA);
  return packets
    .map((packet) => {
      if (!hasDelta && packet.obj.type === PacketType.MESSAGE_START) {
        return (packet.obj as MessageStart).content || "";
      }
      if (packet.obj.type === PacketType.MESSAGE_DELTA) {
        return (packet.obj as MessageDelta).content || "";
      }
      return "";
    })
    .join("");
}

export function getReasoningTextContent(packets: Packet[]): string {
  return packets
    .map((packet) => {
      if (packet.obj.type === PacketType.REASONING_DELTA) {
        return (packet.obj as any).reasoning || "";
      }
      if (packet.obj.type === PacketType.REASONING_START) {
        return (
          (packet.obj as any).reasoning || (packet.obj as any).content || ""
        );
      }
      return "";
    })
    .join("");
}

/** Collects every document carried by a message's search_tool_documents_delta
 * / open_url_documents packets — the same live source MessageToolbar's Sources
 * button already reads (via usePacketProcessor's documentMap) for whether to
 * show at all. DocumentsSidebar needs this too: a message's persisted
 * `documents` field (backend `context_docs`) is only ever populated for
 * internal/connector search, never for web_search/fetch_webpage results, so
 * reading packets directly is the only way those actually reach the sidebar. */
export function getDocumentsFromPackets(packets: Packet[]): OnyxDocument[] {
  const documentMap = new Map<string, OnyxDocument>();

  packets.forEach((packet) => {
    if (packet.obj.type === PacketType.SEARCH_TOOL_DOCUMENTS_DELTA) {
      const docs = (packet.obj as SearchToolDocumentsDelta).documents || [];
      docs.forEach((doc) => {
        if (doc.document_id) documentMap.set(doc.document_id, doc);
      });
    } else if (packet.obj.type === PacketType.FETCH_TOOL_DOCUMENTS) {
      const docs = (packet.obj as FetchToolDocuments).documents || [];
      docs.forEach((doc) => {
        if (doc.document_id) documentMap.set(doc.document_id, doc);
      });
    }
  });

  return Array.from(documentMap.values());
}

export function getCitations(packets: Packet[]): StreamingCitation[] {
  const citations: StreamingCitation[] = [];
  const seenDocIds = new Set<string>();

  packets.forEach((packet) => {
    if (packet.obj.type === PacketType.CITATION_INFO) {
      // Individual citation packet from backend
      const citationInfo = packet.obj as {
        citation_number: number;
        document_id: string;
      };
      if (!seenDocIds.has(citationInfo.document_id)) {
        seenDocIds.add(citationInfo.document_id);
        citations.push({
          citation_num: citationInfo.citation_number,
          document_id: citationInfo.document_id,
        });
      }
    }
  });

  return citations;
}
