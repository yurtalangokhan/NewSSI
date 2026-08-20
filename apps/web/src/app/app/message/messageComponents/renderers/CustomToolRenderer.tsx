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

interface ToolCallState {
  toolName: string;
  args?: CustomToolStart["args"];
  responseType: string | null;
  data: any;
  fileIds: string[] | null;
  hasResult: boolean;
}

/**
 * One group can hold several calls to the same (or different) tool — e.g. a
 * deep-research turn firing several parallel `web_search` calls. Packets
 * within a group are ordered start-then-its-own-deltas per call, so each
 * `custom_tool_start` begins a new call and the deltas that follow (until the
 * next start) belong to it — never collapse them into a single "last delta
 * wins" summary, or every earlier call's query and result just disappears.
 */
function constructCustomToolCalls(packets: CustomToolPacket[]): ToolCallState[] {
  const calls: ToolCallState[] = [];
  let current: ToolCallState | null = null;

  for (const packet of packets) {
    if (packet.obj.type === PacketType.CUSTOM_TOOL_START) {
      const start = packet.obj as CustomToolStart;
      current = {
        toolName: start.tool_name,
        args: start.args,
        responseType: null,
        data: undefined,
        fileIds: null,
        hasResult: false,
      };
      calls.push(current);
    } else if (packet.obj.type === PacketType.CUSTOM_TOOL_DELTA) {
      const delta = packet.obj as CustomToolDelta;
      if (!current) {
        current = {
          toolName: delta.tool_name,
          args: undefined,
          responseType: null,
          data: undefined,
          fileIds: null,
          hasResult: false,
        };
        calls.push(current);
      }
      current.responseType = delta.response_type || null;
      current.data = delta.data;
      current.fileIds = delta.file_ids || current.fileIds;
      current.hasResult = true;
    }
  }

  return calls;
}

function formatToolContent(args: CustomToolStart["args"], data: any): string | null {
  if (data !== undefined && data !== null) {
    if (typeof data === "string") {
      try {
        return JSON.stringify(JSON.parse(data), null, 2);
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
}

function constructCustomToolState(packets: CustomToolPacket[]) {
  const calls = constructCustomToolCalls(packets);
  const toolEnd = packets.find(
    (p) =>
      p.obj.type === PacketType.SECTION_END || p.obj.type === PacketType.ERROR
  )?.obj as SectionEnd | null;

  const toolName = calls[0]?.toolName || "Tool";
  const lastCall = calls[calls.length - 1] || null;
  const responseType = lastCall?.responseType || null;
  const fileIds = calls.flatMap((c) => c.fileIds || []);

  const hasToolActivity = calls.length > 0;
  const isRunning = Boolean(hasToolActivity && !toolEnd);
  const isComplete = Boolean(hasToolActivity && toolEnd);

  return {
    toolName,
    calls,
    responseType,
    fileIds: fileIds.length > 0 ? fileIds : null,
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
  const { toolName, calls, responseType, fileIds, isRunning, isComplete } =
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

  // Each call keeps its own query (args) shown right above its own result
  // (data) — several calls in this group (e.g. parallel web_search queries)
  // must never be collapsed into a single "last result wins" block.
  const formattedCalls = useMemo(
    () =>
      calls.map((call) => ({
        args: formatToolContent(call.args, undefined),
        result: call.hasResult ? formatToolContent(undefined, call.data) : null,
      })),
    [calls]
  );
  const hasAnyContent = formattedCalls.some((c) => c.args || c.result);

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

          {formattedCalls.map((call, idx) => {
            if (!call.args && !call.result) return null;
            const isLast = idx === formattedCalls.length - 1;
            return (
              <div key={idx} className="flex flex-col gap-1">
                {call.args && (
                  <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    {t("customTool.queryLabel")}
                  </div>
                )}
                {call.args && (
                  <div className="text-xs bg-gray-50 dark:bg-gray-800 p-3 rounded border font-mono whitespace-pre-wrap break-all">
                    {call.args}
                  </div>
                )}
                {call.result ? (
                  <div className="text-xs bg-gray-50 dark:bg-gray-800 p-3 rounded border max-h-96 overflow-y-auto font-mono whitespace-pre-wrap break-all">
                    {call.result}
                  </div>
                ) : (
                  isLast &&
                  isRunning && (
                    <div className="text-xs text-gray-500 italic">
                      {t("customTool.waitingForResponse")}
                    </div>
                  )
                )}
              </div>
            );
          })}

          {!fileIds && !hasAnyContent && isRunning && (
            <div className="text-xs text-gray-500 italic">
              {t("customTool.waitingForResponse")}
            </div>
          )}

          {!fileIds && !hasAnyContent && isComplete && (
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
