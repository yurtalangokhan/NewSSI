"use client";

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgMaximize2 } from "@opal/icons";
import { FileIcon } from "@/components/icons/icons";
import Text from "@/refresh-components/texts/Text";
import { formatBytes } from "@/lib/utils";
import TextViewModal from "@/sections/modals/TextViewModal";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import {
  GeneratedFile,
  GeneratedFilePacket,
  PacketType,
} from "../../../services/streamingModels";
import { MessageRenderer } from "../interfaces";

export const GeneratedFileRenderer: MessageRenderer<GeneratedFilePacket, {}> = ({
  packets,
  onComplete,
  children,
}) => {
  const { t } = useTranslation();
  const [previewOpen, setPreviewOpen] = useState(false);
  // The group also carries a synthetic SECTION_END packet once the turn
  // closes, so the file payload is not necessarily the last packet.
  const file = packets.find((p) => p.obj.type === PacketType.GENERATED_FILE)
    ?.obj as GeneratedFile | undefined;

  // The payload arrives fully formed in a single packet — there is no
  // streaming/loading state to wait for, so mark this step complete right away.
  useEffect(() => {
    onComplete();
  }, [onComplete]);

  if (!file) {
    return children([{ icon: null, status: null, content: <></> }]);
  }

  // Reuse the same document-preview modal used for uploaded chat files —
  // opening a generated file behaves identically, no separate download step.
  const presentingDocument: MinimalOnyxDocument = {
    document_id: file.file_id,
    semantic_identifier: file.filename,
  };

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
          <div className="flex items-center border bg-background-tint-00 rounded-12 p-1 gap-1 my-1 w-fit">
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
