"use client";

import React, { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { DownloadCSVIcon, FileIcon } from "@/components/icons/icons";
import Text from "@/refresh-components/texts/Text";
import { formatBytes } from "@/lib/utils";
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

  return children([
    {
      icon: null,
      status: null,
      content: (
        <a
          href={file.download_url}
          download={file.filename}
          className="flex items-center border bg-background-tint-00 rounded-12 p-1 gap-1 my-1 w-fit hover:bg-background-tint-01 transition-colors"
          aria-label={t("generatedFile.downloadAriaLabel", {
            defaultValue: "Download {{filename}}",
            filename: file.filename,
          })}
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
          <div className="p-2">
            <DownloadCSVIcon size={16} />
          </div>
        </a>
      ),
    },
  ]);
};

export default GeneratedFileRenderer;
