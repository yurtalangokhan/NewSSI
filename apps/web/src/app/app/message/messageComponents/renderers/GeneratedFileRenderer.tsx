"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgMaximize2 } from "@opal/icons";
import { FileIcon } from "@/components/icons/icons";
import Text from "@/refresh-components/texts/Text";
import { cn, formatBytes } from "@/lib/utils";
import TextViewModal from "@/sections/modals/TextViewModal";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import {
  DocumentGenerationEnd,
  DocumentGenerationPhase,
  DocumentGenerationProgress,
  DocumentGenerationStart,
  GeneratedFile,
  GeneratedFilePacket,
  PacketType,
} from "../../../services/streamingModels";
import { MessageRenderer } from "../interfaces";
import DocumentGenerationSkeleton from "./DocumentGenerationSkeleton";

interface GenerationState {
  started: boolean;
  phase: DocumentGenerationPhase;
  filename: string | null;
  format: string | null;
  chars: number;
  end: DocumentGenerationEnd | null;
}

/**
 * Collapse the generation lifecycle packets into the current state.
 *
 * `start`/`progress` carry the metadata as soon as the model streams it, so a
 * late packet must never overwrite a known filename with null.
 */
function readGenerationState(packets: GeneratedFilePacket[]): GenerationState {
  const state: GenerationState = {
    started: false,
    phase: "writing",
    filename: null,
    format: null,
    chars: 0,
    end: null,
  };

  for (const { obj } of packets) {
    switch (obj.type) {
      case PacketType.DOCUMENT_GENERATION_START: {
        const start = obj as DocumentGenerationStart;
        state.started = true;
        state.phase = start.phase ?? "writing";
        state.filename = start.filename ?? state.filename;
        state.format = start.format ?? state.format;
        // A fresh attempt supersedes the outcome of the previous one — the
        // agent retries after a rejected tool call.
        state.end = null;
        state.chars = 0;
        break;
      }
      case PacketType.DOCUMENT_GENERATION_PROGRESS: {
        const progress = obj as DocumentGenerationProgress;
        state.started = true;
        state.phase = progress.phase ?? state.phase;
        state.filename = progress.filename ?? state.filename;
        state.format = progress.format ?? state.format;
        state.chars = Math.max(state.chars, progress.chars ?? 0);
        break;
      }
      case PacketType.DOCUMENT_GENERATION_END: {
        state.end = obj as DocumentGenerationEnd;
        break;
      }
    }
  }

  return state;
}

export const GeneratedFileRenderer: MessageRenderer<GeneratedFilePacket, {}> = ({
  packets,
  onComplete,
  stopPacketSeen,
  children,
}) => {
  const { t } = useTranslation();
  const [previewOpen, setPreviewOpen] = useState(false);
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
  const presentingDocument: MinimalOnyxDocument | null = useMemo(() => {
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
          content: (
            <DocumentGenerationSkeleton
              phase={generation.phase}
              filename={generation.filename}
              format={generation.format}
              chars={generation.chars}
            />
          ),
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
          {previewOpen && (
            <TextViewModal
              presentingDocument={presentingDocument}
              onClose={() => setPreviewOpen(false)}
            />
          )}
          <div
            className={cn(
              "flex items-center border bg-background-tint-00 rounded-12 p-1 gap-1 my-1 w-fit",
              // Only when this card just replaced a skeleton — cards restored
              // from history should not animate on page load.
              generation.started && "animate-fade-in-scale"
            )}
          >
            <div className="p-2 bg-background-tint-01 rounded-08">
              <FileIcon size={20} />
            </div>
            <div className="flex flex-col px-2">
              <Text as="p" secondaryAction>
                {file.filename}
              </Text>
              <Text as="p" secondaryBody text03>
                {formatBytes(file.size_bytes)}
              </Text>
            </div>
            <Button
              aria-label={t("generatedFile.openAriaLabel", {
                filename: file.filename,
              })}
              onClick={() => setPreviewOpen(true)}
              icon={SvgMaximize2}
              prominence="tertiary"
              size="sm"
            />
          </div>
        </>
      ),
    },
  ]);
};

export default GeneratedFileRenderer;
