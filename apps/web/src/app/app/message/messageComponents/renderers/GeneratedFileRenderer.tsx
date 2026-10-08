"use client";

import { useEffect, useMemo, useState } from "react";
import TextViewModal from "@/sections/modals/TextViewModal";
import { MinimalAtlasDocument } from "@/lib/search/interfaces";
import {
  GeneratedFile,
  GeneratedFilePacket,
  PacketType,
} from "@/lib/api/domains/chat/streaming-types";
import { readGenerationState } from "@/app/app/message/messageComponents/renderers/documentGenerationState";
import { DocumentCard } from "@/app/app/message/messageComponents/renderers/DocumentCard";
import { DocumentProgressCard } from "@/app/app/message/messageComponents/renderers/DocumentProgressCard";
import { MessageRenderer } from "../interfaces";

export const GeneratedFileRenderer: MessageRenderer<
  GeneratedFilePacket,
  {}
> = ({ packets, onComplete, stopPacketSeen, children }) => {
  const [fallbackOpen, setFallbackOpen] = useState(false);
  // The group also carries a synthetic SECTION_END packet once the turn
  // closes, so the file payload is not necessarily the last packet.
  const file = packets.find((p) => p.obj.type === PacketType.GENERATED_FILE)
    ?.obj as GeneratedFile | undefined;

  const generation = readGenerationState(packets);
  // A generation that is still writing has nothing to hand off yet — reporting
  // completion early would let the message be marked as finished.
  const settled = Boolean(file) || generation.end !== null || stopPacketSeen;

  useEffect(() => {
    if (settled) {
      onComplete();
    }
  }, [settled, onComplete]);

  // Reuse the same document-preview modal used for uploaded chat files —
  // opening a generated file behaves identically, no separate download step.
  const presentingDocument: MinimalAtlasDocument | null = useMemo(() => {
    if (!file) return null;
    return {
      document_id: file.file_id,
      semantic_identifier: file.filename,
    };
  }, [file?.file_id, file?.filename]);

  if (!file || !presentingDocument) {
    // A generation that produced no file leaves nothing behind. The agent is
    // told what went wrong and either retries or explains it in its reply, so
    // a notice here would only interrupt that answer — often twice, since each
    // rejected attempt is its own generation.
    // Still writing/rendering: show the skeleton so the stream never looks
    // frozen while the model produces the document body.
    if (generation.started && generation.end === null && !stopPacketSeen) {
      return children([
        {
          icon: null,
          status: null,
          content: <DocumentProgressCard state={generation} />,
        },
      ]);
    }

    return children([{ icon: null, status: null, content: <></> }]);
  }

  return children([
    {
      icon: null,
      status: null,
      content: (
        <>
          {/* Only where no document panel is mounted (e.g. a shared chat). */}
          {fallbackOpen && (
            <TextViewModal
              presentingDocument={presentingDocument}
              onClose={() => setFallbackOpen(false)}
            />
          )}
          <DocumentCard
            file={file}
            isLive={generation.started}
            onFallbackOpen={() => setFallbackOpen(true)}
          />
        </>
      ),
    },
  ]);
};

export default GeneratedFileRenderer;
