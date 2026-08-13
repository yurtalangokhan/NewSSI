"use client";

import React, { useEffect, useMemo } from "react";
import { FiExternalLink, FiDownload, FiTool } from "react-icons/fi";
import { useTranslation } from "react-i18next";
import {
  PacketType,
  CustomToolPacket,
  CustomToolStart,
  CustomToolDelta,
  SectionEnd,
} from "../../../services/streamingModels";
import { MessageRenderer, RenderType } from "../interfaces";
import { buildImgUrl } from "../../../components/files/images/utils";

function constructCustomToolState(packets: CustomToolPacket[]) {
  const toolStart = packets.find(
    (p) => p.obj.type === PacketType.CUSTOM_TOOL_START
  )?.obj as CustomToolStart | null;
  const toolDeltas = packets
    .filter((p) => p.obj.type === PacketType.CUSTOM_TOOL_DELTA)
    .map((p) => p.obj as CustomToolDelta);
  const toolEnd = packets.find(
    (p) =>
      p.obj.type === PacketType.SECTION_END || p.obj.type === PacketType.ERROR
  )?.obj as SectionEnd | null;

  const toolName = toolStart?.tool_name || toolDeltas[0]?.tool_name || "Tool";
  const args = toolStart?.args;
  const latestDelta = toolDeltas[toolDeltas.length - 1] || null;
  const responseType = latestDelta?.response_type || null;
  const data = latestDelta?.data;
  const fileIds = latestDelta?.file_ids || null;

  const hasToolActivity = Boolean(toolStart || toolDeltas.length > 0);
  const isRunning = Boolean(hasToolActivity && !toolEnd);
  const isComplete = Boolean(hasToolActivity && toolEnd);

  return {
    toolName,
    args,
    responseType,
    data,
    fileIds,
    isRunning,
    isComplete,
  };
}

export const CustomToolRenderer: MessageRenderer<CustomToolPacket, {}> = ({
  packets,
  onComplete,
  renderType,
  children,
}) => {
  const { t } = useTranslation();
  const { toolName, args, responseType, data, fileIds, isRunning, isComplete } =
    constructCustomToolState(packets);

  useEffect(() => {
    if (isComplete) {
      onComplete();
    }
  }, [isComplete, onComplete]);

  const status = useMemo(() => {
    if (isComplete) {
      if (responseType === "image")
        return t("customTool.returnedImages", { toolName });
      if (responseType === "csv")
        return t("customTool.returnedFile", { toolName });
      return t("customTool.completed", { toolName });
    }
    if (isRunning) return t("customTool.running", { toolName });
    return null;
  }, [toolName, responseType, isComplete, isRunning, t]);

  const icon = FiTool;

  const formattedData = useMemo(() => {
    if (data !== undefined && data !== null) {
      if (typeof data === "string") {
        try {
          const parsed = JSON.parse(data);
          return JSON.stringify(parsed, null, 2);
        } catch {
          return data;
        }
      }
      return JSON.stringify(data, null, 2);
    }
    if (args !== undefined && args !== null) {
      let parsedArgs: any = args;
      if (typeof args === "string") {
        try {
          parsedArgs = JSON.parse(args);
        } catch {
          return args;
        }
      }
      if (typeof parsedArgs === "object" && parsedArgs !== null) {
        const cleaned: Record<string, any> = { ...parsedArgs };
        if (typeof cleaned.content === "string" && cleaned.content.length > 150) {
          cleaned.content = `[Doküman İçeriği: ${cleaned.content.length} karakter]`;
        }
        return JSON.stringify(cleaned, null, 2);
      }
      return String(parsedArgs);
    }
    return null;
  }, [data, args]);

  if (renderType === RenderType.COMPACT) {
    return children([
      {
        icon,
        status: status,
        supportsCollapsible: true,
        content: <></>,
      },
    ]);
  }

  return children([
    {
      icon,
      status,
      supportsCollapsible: true,
      content: (
        <div className="flex flex-col gap-3">
          {fileIds && fileIds.length > 0 && (
            <div className="text-sm text-muted-foreground flex flex-col gap-2">
              {fileIds.map((fid, idx) => (
                <div key={fid} className="flex items-center gap-2 flex-wrap">
                  <span className="whitespace-nowrap">
                    {t("customTool.fileLabel", { index: idx + 1 })}
                  </span>
                  <a
                    href={buildImgUrl(fid)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline whitespace-nowrap"
                  >
                    <FiExternalLink className="w-3 h-3" />{" "}
                    {t("customTool.openButton")}
                  </a>
                  <a
                    href={buildImgUrl(fid)}
                    download
                    className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline whitespace-nowrap"
                  >
                    <FiDownload className="w-3 h-3" />{" "}
                    {t("customTool.downloadButton")}
                  </a>
                </div>
              ))}
            </div>
          )}

          {formattedData && (
            <div className="text-xs bg-gray-50 dark:bg-gray-800 p-3 rounded border max-h-96 overflow-y-auto font-mono whitespace-pre-wrap break-all">
              {formattedData}
            </div>
          )}

          {!fileIds && !formattedData && isRunning && (
            <div className="text-xs text-gray-500 italic">
              {t("customTool.waitingForResponse")}
            </div>
          )}

          {!fileIds && !formattedData && isComplete && (
            <div className="text-xs text-gray-500 italic">
              {t("customTool.completed", { toolName })}
            </div>
          )}
        </div>
      ),
    },
  ]);
};

export default CustomToolRenderer;
