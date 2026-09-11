"use client";

import React, { useState, useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  SvgChevronDown,
  SvgChevronUp,
  SvgTerminal,
  SvgCheck,
  SvgCopy,
  SvgSparkle,
  SvgMaximize2,
  SvgLoader,
  SvgAlertCircle,
} from "@opal/icons";
import { cn } from "@/lib/utils";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { formatRunTime } from "../utils/formatRunTime";
import type { NodeExecutionData } from "../types/execution";
import { StageOutputModal } from "@/app/app/message/messageComponents/timeline/FlowStageSections";

export interface NodeExecutionDrawerProps {
  nodeId: string;
  data: NodeExecutionData;
  onToggle?: (expanded: boolean) => void;
}

export function NodeExecutionDrawer({
  nodeId,
  data,
  onToggle,
}: NodeExecutionDrawerProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  // Iteration tracking: follow latest running iteration unless user explicitly selected one
  const hasMultipleIterations = Boolean(
    data.iterations && data.iterations.length > 1
  );
  const [userSelectedIteration, setUserSelectedIteration] = useState<
    number | null
  >(null);
  const latestIterationNum =
    data.iterations && data.iterations.length > 0
      ? data.iterations[data.iterations.length - 1]!.iteration
      : 1;
  const selectedIterationNum = userSelectedIteration ?? latestIterationNum;

  const activeIterationData = useMemo(() => {
    if (!hasMultipleIterations || !data.iterations) return null;
    return (
      data.iterations.find((it) => it.iteration === selectedIterationNum) ||
      data.iterations[data.iterations.length - 1]
    );
  }, [hasMultipleIterations, data.iterations, selectedIterationNum]);

  const currentThinking = useMemo(() => {
    if (activeIterationData) {
      return activeIterationData.thinking || "";
    }
    return data.thinking || "";
  }, [activeIterationData, data.thinking]);

  const currentTools = useMemo(() => {
    if (activeIterationData) {
      return activeIterationData.tools || [];
    }
    return data.tools || [];
  }, [activeIterationData, data.tools]);

  const currentOutput = useMemo(() => {
    if (activeIterationData) {
      return activeIterationData.output || "";
    }
    return data.output || "";
  }, [activeIterationData, data.output]);

  // Active tab selection: follow live phase if user hasn't explicitly chosen a tab
  const [userSelectedTab, setUserSelectedTab] = useState<
    "thinking" | "tools" | "output" | null
  >(null);

  const activeTab = useMemo((): "thinking" | "tools" | "output" => {
    if (userSelectedTab !== null) {
      return userSelectedTab;
    }
    // Live streaming phase auto-tracking:
    // 1. If tools are actively running, show tools
    if (
      currentTools.length > 0 &&
      currentTools.some((t) => t.status === "running")
    ) {
      return "tools";
    }
    // 2. If output is actively streaming while running and thinking/tools are finished, show output
    if (
      data.status === "running" &&
      currentOutput.trim() &&
      (!currentThinking.trim() || currentTools.length > 0)
    ) {
      return "output";
    }
    // 3. Normal order (or finished state): thinking -> tools -> output
    if (currentThinking.trim()) return "thinking";
    if (currentTools.length > 0) return "tools";
    return "output";
  }, [
    userSelectedTab,
    data.status,
    currentOutput,
    currentTools,
    currentThinking,
  ]);

  const handleToggle = useCallback(
    (e: React.MouseEvent | React.KeyboardEvent) => {
      e.stopPropagation();
      if ("preventDefault" in e) e.preventDefault();
      const next = !isExpanded;
      setIsExpanded(next);
      onToggle?.(next);
    },
    [isExpanded, onToggle]
  );

  const copyToClipboard = useCallback((text: string, type: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    });
  }, []);

  const totalToolCalls = useMemo(() => {
    return currentTools.reduce((acc, tool) => acc + (tool.callCount || 1), 0);
  }, [currentTools]);

  const thinkingWordCount = useMemo(() => {
    if (!currentThinking.trim()) return 0;
    return currentThinking.trim().split(/\s+/).length;
  }, [currentThinking]);

  // Check if there is anything to show
  const hasContent = Boolean(
    currentThinking.trim() ||
      currentTools.length > 0 ||
      currentOutput.trim() ||
      data.status === "running"
  );

  if (!hasContent) {
    return null;
  }

  return (
    <div
      data-testid={`node-execution-drawer-${nodeId}`}
      className="w-full border-t border-canvas-border bg-card/95 transition-all duration-200 select-text pointer-events-auto nodrag nopan"
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {/* Collapsed Summary Bar */}
      {!isExpanded && (
        <div
          role="button"
          tabIndex={0}
          onClick={handleToggle}
          onMouseDown={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              handleToggle(e);
            }
          }}
          className="group/drawer flex w-full items-center justify-between px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted/40 cursor-pointer nodrag nopan pointer-events-auto select-none"
        >
          <div className="flex flex-wrap items-center gap-1.5 overflow-hidden">
            {currentThinking.trim() && (
              <span className="inline-flex items-center gap-1 rounded bg-action-link-01 px-1.5 py-0.5 text-[10px] font-medium text-action-link-05 border border-action-link-02">
                <SvgSparkle className="size-2.5 shrink-0" />
                <span>
                  {t("chat.nodeDrawer.thinking", "Düşünce")}
                  {thinkingWordCount > 0 &&
                    ` (${thinkingWordCount} ${t(
                      "chat.nodeDrawer.words",
                      "kelime"
                    )})`}
                </span>
              </span>
            )}

            {currentTools.length > 0 && (
              <span className="inline-flex items-center gap-1 rounded bg-action-link-01 px-1.5 py-0.5 text-[10px] font-medium text-action-link-05 border border-action-link-02">
                <SvgTerminal className="size-2.5 shrink-0" />
                <span>
                  {totalToolCalls} {t("chat.nodeDrawer.toolsCount", "araç")}
                </span>
              </span>
            )}

            {currentOutput.trim() && (
              <span className="inline-flex items-center gap-1 rounded bg-theme-green-01 px-1.5 py-0.5 text-[10px] font-medium text-theme-green-05 border border-theme-green-02">
                <SvgCheck className="size-2.5 shrink-0" />
                <span>{t("chat.nodeDrawer.output", "Çıktı")}</span>
              </span>
            )}

            {data.status === "running" && (
              <span className="inline-flex items-center gap-1 text-[10px] text-primary animate-pulse font-medium">
                <SvgLoader className="size-2.5 animate-spin shrink-0" />
                <span>{t("chat.stageRunning", "Çalışıyor")}</span>
              </span>
            )}
          </div>

          <div className="ml-1 flex items-center gap-1 text-muted-foreground group-hover/drawer:text-foreground">
            <span className="text-[10px] font-medium">
              {t("chat.nodeDrawer.expand", "Detaylar")}
            </span>
            <SvgChevronDown className="size-3 shrink-0 transition-transform" />
          </div>
        </div>
      )}

      {/* Expanded Drawer Content */}
      {isExpanded && (
        <div className="flex flex-col border-t border-canvas-border nodrag nopan nowheel animate-in fade-in-50 duration-200">
          {/* Drawer Header & Tabs */}
          <div className="flex items-center justify-between border-b border-canvas-border bg-muted/30 px-2 py-1">
            <div className="flex items-center gap-1">
              <div
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  setUserSelectedTab("thinking");
                }}
                className={cn(
                  "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors",
                  activeTab === "thinking"
                    ? "bg-card text-foreground shadow-2xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <SvgSparkle className="size-2.5 text-action-link-05" />
                <span>{t("chat.nodeDrawer.thinking", "Düşünce")}</span>
                {currentThinking.trim() && (
                  <span className="size-1.5 rounded-full bg-action-link-05 shrink-0" />
                )}
              </div>

              <div
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  setUserSelectedTab("tools");
                }}
                className={cn(
                  "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors",
                  activeTab === "tools"
                    ? "bg-card text-foreground shadow-2xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <SvgTerminal className="size-2.5 text-action-link-05" />
                <span>
                  {t("chat.nodeDrawer.tools", "Araçlar")}
                  {totalToolCalls > 0 && ` (${totalToolCalls})`}
                </span>
              </div>

              <div
                role="button"
                tabIndex={0}
                onClick={(e) => {
                  e.stopPropagation();
                  setUserSelectedTab("output");
                }}
                className={cn(
                  "flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors",
                  activeTab === "output"
                    ? "bg-card text-foreground shadow-2xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <SvgCheck className="size-2.5 text-theme-green-05" />
                <span>{t("chat.nodeDrawer.output", "Çıktı")}</span>
                {currentOutput.trim() && (
                  <span className="size-1.5 rounded-full bg-theme-green-05 shrink-0" />
                )}
              </div>
            </div>

            <div
              role="button"
              tabIndex={0}
              onClick={handleToggle}
              aria-label={t("chat.nodeDrawer.collapse", "Kapat")}
              className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <SvgChevronUp className="size-3" />
            </div>
          </div>

          {/* Multiple Iterations / Loop Pills */}
          {hasMultipleIterations && data.iterations && (
            <div className="flex items-center gap-1 border-b border-canvas-border/60 bg-muted/10 px-2 py-1 overflow-x-auto">
              <span className="text-[10px] text-muted-foreground mr-1 font-medium">
                {t("chat.flowTimeline.loopLabel", { name: "Döngü" })}:
              </span>
              {data.iterations.map((it) => (
                <div
                  key={it.iteration}
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    e.stopPropagation();
                    setUserSelectedIteration(it.iteration);
                  }}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors",
                    selectedIterationNum === it.iteration
                      ? "bg-primary text-primary-foreground font-semibold"
                      : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  {t("chat.flowTimeline.iteration", "Tur {{turn}}", {
                    turn: it.iteration,
                  })}
                  {it.durationMs ? ` · ${formatRunTime(it.durationMs)}` : ""}
                </div>
              ))}
            </div>
          )}

          {/* Active Tab Content Area */}
          <div className="p-3 max-h-64 overflow-y-auto flex flex-col gap-2">
            {/* 1. THINKING TAB */}
            {activeTab === "thinking" && (
              <div className="flex flex-col gap-2">
                {currentThinking.trim() ? (
                  <>
                    <div className="relative rounded-md border-l-2 border-action-link-02 bg-muted/20 p-2.5 text-[11px] font-mono leading-relaxed text-muted-foreground whitespace-pre-wrap select-text max-h-48 overflow-y-auto">
                      {currentThinking}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                      <span>
                        {thinkingWordCount}{" "}
                        {t("chat.nodeDrawer.words", "kelime")}
                      </span>
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          copyToClipboard(currentThinking, "thinking");
                        }}
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground transition-colors"
                      >
                        {copied === "thinking" ? (
                          <>
                            <SvgCheck className="size-2.5 text-theme-green-05" />
                            <span className="text-theme-green-05">
                              {t("chat.copied", "Kopyalandı")}
                            </span>
                          </>
                        ) : (
                          <>
                            <SvgCopy className="size-2.5" />
                            <span>
                              {t(
                                "chat.nodeDrawer.copyThinking",
                                "Düşünceyi Kopyala"
                              )}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="py-4 text-center text-xs text-muted-foreground italic">
                    {t(
                      "chat.nodeDrawer.noThinking",
                      "Bu aşama için düşünce kaydı bulunmuyor."
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 2. TOOLS TAB */}
            {activeTab === "tools" && (
              <div className="flex flex-col gap-2">
                {currentTools.length > 0 ? (
                  currentTools.map((tool) => (
                    <div
                      key={tool.toolName}
                      className="flex flex-col rounded-md border border-canvas-border/80 bg-background/60 p-2 text-xs"
                    >
                      <div className="flex items-center justify-between pb-1 border-b border-canvas-border/40">
                        <div className="flex items-center gap-1.5">
                          <SvgTerminal className="size-3 text-action-link-05" />
                          <span className="font-semibold text-foreground text-[11px]">
                            {tool.label || tool.toolName}
                          </span>
                          {tool.callCount > 1 && (
                            <span className="rounded bg-action-link-01 px-1 py-0.2 text-[9px] font-bold text-action-link-05">
                              {tool.callCount}x
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          {tool.durationMs && (
                            <span className="font-mono text-[10px] text-muted-foreground">
                              {formatRunTime(tool.durationMs)}
                            </span>
                          )}
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5 text-[9px] font-medium",
                              tool.status === "running"
                                ? "bg-theme-amber-01 text-theme-amber-05"
                                : tool.status === "error"
                                  ? "bg-destructive/15 text-destructive"
                                  : "bg-theme-green-01 text-theme-green-05"
                            )}
                          >
                            {tool.status === "running"
                              ? t("chat.stageRunning", "Çalışıyor")
                              : tool.status === "error"
                                ? t("chat.stageFailed", "Hata")
                                : t("chat.stageCompleted", "Tamamlandı")}
                          </span>
                        </div>
                      </div>

                      {/* Tool Invocations Details */}
                      <div className="flex flex-col gap-1.5 pt-1.5">
                        {tool.invocations.map((inv) => (
                          <div
                            key={inv.index}
                            className="flex flex-col gap-1 rounded bg-muted/30 p-1.5 text-[11px] font-mono"
                          >
                            {inv.input !== undefined && (
                              <div className="flex flex-col">
                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                                  {t("chat.nodeDrawer.toolInput", "Girdi")}:
                                </span>
                                <div className="mt-0.5 max-h-24 overflow-y-auto whitespace-pre-wrap rounded bg-card/80 p-1 text-[10px] text-foreground select-text border border-canvas-border/40">
                                  {typeof inv.input === "string"
                                    ? inv.input
                                    : JSON.stringify(inv.input, null, 2)}
                                </div>
                              </div>
                            )}

                            {inv.output !== undefined && (
                              <div className="flex flex-col">
                                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                                  {t("chat.nodeDrawer.toolOutput", "Sonuç")}:
                                </span>
                                <div className="mt-0.5 max-h-28 overflow-y-auto whitespace-pre-wrap rounded bg-card/80 p-1 text-[10px] text-foreground select-text border border-canvas-border/40">
                                  {typeof inv.output === "string"
                                    ? inv.output
                                    : JSON.stringify(inv.output, null, 2)}
                                </div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="py-4 text-center text-xs text-muted-foreground italic">
                    {t(
                      "chat.nodeDrawer.noTools",
                      "Bu aşamada harici araç çağrılmadı."
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 3. OUTPUT TAB */}
            {activeTab === "output" && (
              <div className="flex flex-col gap-2">
                {currentOutput.trim() ? (
                  <>
                    <div className="rounded-md border border-canvas-border/60 bg-background/50 p-2.5 text-xs select-text max-h-48 overflow-y-auto leading-normal">
                      <MinimalMarkdown content={currentOutput} />
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1">
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          copyToClipboard(currentOutput, "output");
                        }}
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-muted hover:text-foreground transition-colors"
                      >
                        {copied === "output" ? (
                          <>
                            <SvgCheck className="size-2.5 text-theme-green-05" />
                            <span className="text-theme-green-05">
                              {t("chat.copied", "Kopyalandı")}
                            </span>
                          </>
                        ) : (
                          <>
                            <SvgCopy className="size-2.5" />
                            <span>
                              {t(
                                "chat.nodeDrawer.copyOutput",
                                "Çıktıyı Kopyala"
                              )}
                            </span>
                          </>
                        )}
                      </div>

                      <div
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsModalOpen(true);
                        }}
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-primary hover:bg-primary/10 transition-colors font-medium"
                      >
                        <SvgMaximize2 className="size-2.5" />
                        <span>{t("chat.nodeDrawer.maximize", "Büyüt")}</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="py-4 text-center text-xs text-muted-foreground italic">
                    {t("chat.nodeDrawer.noOutput", "Henüz çıktı üretilmedi.")}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Fullscreen Output Modal */}
      {isModalOpen && currentOutput && (
        <StageOutputModal
          open={isModalOpen}
          onOpenChange={setIsModalOpen}
          title={data.label || nodeId}
          text={currentOutput}
        />
      )}
    </div>
  );
}
