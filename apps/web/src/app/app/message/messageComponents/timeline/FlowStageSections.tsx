"use client";

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  SvgCheck,
  SvgLoader,
  SvgChevronDown,
  SvgChevronRight,
  SvgAlertCircle,
  SvgMaximize2,
  SvgDownload,
  SvgTerminal,
} from "@opal/icons";
import { Button } from "@opal/components";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import Modal from "@/refresh-components/Modal";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { formatRunTime } from "@/components/flow-canvas/utils/formatRunTime";
import { FullChatState } from "../interfaces";
import {
  StageGroup,
  LoopGroup,
  TimelineSection,
} from "./hooks/flowStageGrouping";
import { ExpandedTimelineContent } from "./ExpandedTimelineContent";
import { isToolInvocationPackets } from "./packetHelpers";

// ---------------------------------------------------------------------------
// StageOutputBlock — an intermediate stage's own message text, rendered
// thinking-style under a small "Çıktı" label. Long output can be expanded
// inline (chevron) or opened full-size in a modal (maximize button).
// ---------------------------------------------------------------------------

/** Save one stage's output as a Markdown (.md) file, named after the stage. */
function downloadStageOutput(title: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const name =
      title
        .replace(/[^a-z0-9]/gi, "_")
        .toLowerCase()
        .replace(/^_+|_+$/g, "") || "cikti";
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function StageOutputModal({
  open,
  onOpenChange,
  title,
  text,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  title: string;
  text: string;
}) {
  const { t } = useTranslation();
  const lineCount = text.split("\n").length;
  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content height="lg" width="md-sm" preventAccidentalClose={false}>
        <Modal.Header
          title={title}
          description={t("chat.flowStageOutput", { defaultValue: "Çıktı" })}
          onClose={() => onOpenChange(false)}
        />
        <Modal.Body>
          <div className="w-full text-text-04 [&_*]:!text-text-04">
            <MinimalMarkdown content={text} />
          </div>
        </Modal.Body>
        <Modal.Footer>
          <div className="mr-auto px-2">
            <Text as="span" mainUiMuted text03>
              {t("filePreview.lines", { count: lineCount })}
            </Text>
          </div>
          <CopyIconButton
            prominence="tertiary"
            size="sm"
            getCopyText={() => text}
            tooltip={t("filePreview.copyContent")}
          />
          <Button
            prominence="tertiary"
            size="sm"
            icon={SvgDownload}
            tooltip={t("filePreview.download")}
            onClick={() => downloadStageOutput(title, text)}
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}

function StageOutputBlock({ text, title }: { text: string; title?: string }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  if (!text.trim()) return null;
  const long = text.length > 600;
  const outputLabel = t("chat.flowStageOutput", { defaultValue: "Çıktı" });
  return (
    <div
      className="mt-1.5 pl-[var(--timeline-common-text-padding)]"
      data-testid="stage-output-block"
    >
      <button
        type="button"
        onClick={() => long && setExpanded((v) => !v)}
        className={cn(
          "mb-0.5 flex items-center gap-1 text-text-03",
          long && "hover:text-text-02"
        )}
      >
        <Text
          secondaryBody
          className="text-[10px] uppercase tracking-wide text-inherit"
        >
          {outputLabel}
        </Text>
        {long &&
          (expanded ? (
            <SvgChevronDown className="h-3 w-3" />
          ) : (
            <SvgChevronRight className="h-3 w-3" />
          ))}
      </button>
      <div className="flex w-full">
        <div
          className={cn(
            "min-w-0 flex-1 text-text-02 [&_*]:!text-text-02",
            long && !expanded && "line-clamp-6 overflow-hidden"
          )}
          data-testid="stage-output-text"
        >
          <MinimalMarkdown content={text} />
        </div>
        <div className="flex w-8 shrink-0 justify-end self-end">
          <Button
            prominence="tertiary"
            size="sm"
            icon={SvgMaximize2}
            aria-label={t("common.viewFullText")}
            data-testid="stage-output-maximize"
            onClick={() => setModalOpen(true)}
          />
        </div>
      </div>
      <StageOutputModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={title?.trim() || outputLabel}
        text={text}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// StageGroupSection — one numbered, collapsible agent/model stage.
// ---------------------------------------------------------------------------

function StageStatusIcon({ status }: { status: StageGroup["status"] }) {
  if (status === "running") {
    return (
      <SvgLoader
        className="h-3.5 w-3.5 shrink-0 animate-spin text-status-info-05"
        data-testid="stage-status-running"
      />
    );
  }
  if (status === "error" || status === "cancelled") {
    return (
      <SvgAlertCircle
        className="h-3.5 w-3.5 shrink-0 stroke-status-warning-05"
        data-testid="stage-status-warning"
      />
    );
  }
  return null;
}

interface SectionHeaderProps {
  expanded: boolean;
  /** When omitted the header renders as static text (no collapse control). */
  onToggle?: () => void;
  icon?: React.ReactNode;
  label: React.ReactNode;
  meta?: React.ReactNode;
  toolCount?: number;
}

function SectionHeader({
  expanded,
  onToggle,
  icon,
  label,
  meta,
  toolCount = 0,
}: SectionHeaderProps) {
  const Chevron = expanded ? SvgChevronDown : SvgChevronRight;
  const inner = (
    <>
      <Chevron className="h-3.5 w-3.5 shrink-0 text-text-03 transition-colors group-hover:text-text-04" />
      {icon}
      <div className="flex min-w-0 flex-1 items-center">
        <Text mainUiAction text05 className="truncate font-medium text-text-05">
          {label}
        </Text>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2 pl-2 text-text-03">
        {toolCount > 0 && (
          <span className="flex shrink-0 items-center gap-1 rounded bg-background-neutral-01/60 px-1.5 py-0.5 text-text-03">
            <SvgTerminal className="h-3 w-3" />
            <Text secondaryBody text03 className="font-mono text-xs">
              {toolCount}
            </Text>
          </span>
        )}
        {meta && (
          <Text secondaryBody text03 className="shrink-0 font-mono text-xs">
            {meta}
          </Text>
        )}
      </div>
    </>
  );
  const className =
    "group flex w-full items-center gap-2 rounded-08 px-2 py-1.5 text-left transition-colors hover:bg-background-tint-00";

  if (!onToggle) {
    return <div className={className}>{inner}</div>;
  }
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={cn(className, "cursor-pointer")}
    >
      {inner}
    </button>
  );
}

export interface StageGroupSectionProps {
  group: StageGroup;
  index: string | number;
  chatState: FullChatState;
  expanded: boolean;
  /** Omitted for a section that is always shown expanded (loop iterations). */
  onToggle?: () => void;
}

export function StageGroupSection({
  group,
  index,
  chatState,
  expanded,
  onToggle,
}: StageGroupSectionProps) {
  // Count only tool-invocation steps — reasoning / output steps must not
  // inflate the wrench badge.
  const toolCount = group.turnGroups.reduce(
    (n, tg) =>
      n + tg.steps.filter((s) => isToolInvocationPackets(s.packets)).length,
    0
  );
  return (
    <div data-stage-section>
      <SectionHeader
        expanded={expanded}
        onToggle={onToggle}
        icon={<StageStatusIcon status={group.status} />}
        label={
          <>
            {index}. {group.label}
          </>
        }
        meta={
          group.durationMs != null ? formatRunTime(group.durationMs) : undefined
        }
        toolCount={toolCount}
      />
      {expanded && (group.turnGroups.length > 0 || group.outputText.trim()) && (
        <div className="ml-[12px] border-l border-border-01 pl-3 pt-0.5">
          {group.turnGroups.length > 0 && (
            <ExpandedTimelineContent
              turnGroups={group.turnGroups}
              chatState={chatState}
              stopPacketSeen
              isSingleStep={false}
              userStopped={false}
              showDoneStep={false}
              showStoppedStep={false}
              hasDoneIndicator={false}
            />
          )}
          <StageOutputBlock
            text={group.outputText}
            title={`${index}. ${group.label}`}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LoopGroupSection
// ---------------------------------------------------------------------------

export interface LoopGroupSectionProps {
  group: LoopGroup;
  index: string | number;
  chatState: FullChatState;
  expanded: boolean;
  onToggle: () => void;
}

export function LoopGroupSection({
  group,
  index,
  chatState,
  expanded,
  onToggle,
}: LoopGroupSectionProps) {
  const { t } = useTranslation();
  const [openIter, setOpenIter] = useState<Record<number, boolean>>({});
  const loopLabel = t("chat.flowTimeline.loopLabel", "{{name}} Döngüsü", {
    name: group.label,
  });
  const iterationCountLabel = t(
    "chat.flowTimeline.iterationCount",
    "{{count}} tur",
    {
      count: group.iterationCount,
    }
  );
  return (
    <div data-loop-section>
      <SectionHeader
        expanded={expanded}
        onToggle={onToggle}
        label={
          <>
            {index}. {loopLabel}
          </>
        }
        meta={
          iterationCountLabel +
          (group.durationMs != null
            ? ` · ${formatRunTime(group.durationMs)}`
            : "")
        }
      />
      {expanded && (
        <div className="ml-[12px] border-l border-border-01 pl-2 pt-0.5">
          {group.iterations.map((iterationStages, i) => {
            const turn = i + 1;
            const iterOpen = openIter[turn] ?? turn === group.iterations.length;
            return (
              <div key={turn} className="mb-0.5">
                <SectionHeader
                  expanded={iterOpen}
                  onToggle={() =>
                    setOpenIter((prev) => ({ ...prev, [turn]: !iterOpen }))
                  }
                  label={
                    <Text secondaryBody text02>
                      {t("chat.flowTimeline.iteration", "Tur {{turn}}", {
                        turn,
                      })}
                    </Text>
                  }
                />
                {iterOpen &&
                  iterationStages.map((s) => (
                    <StageGroupSection
                      key={s.stageKey}
                      group={s}
                      index={`${index}.${turn}`}
                      chatState={chatState}
                      expanded
                    />
                  ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FlowStageSections
// ---------------------------------------------------------------------------

export interface FlowStageSectionsProps {
  sections: TimelineSection[];
  chatState: FullChatState;
}

export function FlowStageSections({
  sections,
  chatState,
}: FlowStageSectionsProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (sections.length === 0) return null;

  const keyOf = (sec: TimelineSection, i: number) =>
    sec.kind === "stage" ? sec.stageKey : `loop-${i}`;

  const defaultOpen = (sec: TimelineSection) =>
    sec.kind === "stage" && sec.status === "running";

  const isOpen = (sec: TimelineSection, i: number) => {
    const k = keyOf(sec, i);
    return k in open ? open[k] ?? false : defaultOpen(sec);
  };

  const toggle = (sec: TimelineSection, i: number) =>
    setOpen((prev) => {
      const k = keyOf(sec, i);
      const cur = k in prev ? prev[k] : defaultOpen(sec);
      return { ...prev, [k]: !cur };
    });

  return (
    <div className="flex flex-col gap-0.5" data-testid="flow-stage-sections">
      {sections.map((sec, i) =>
        sec.kind === "loop" ? (
          <LoopGroupSection
            key={keyOf(sec, i)}
            group={sec}
            index={i + 1}
            chatState={chatState}
            expanded={isOpen(sec, i)}
            onToggle={() => toggle(sec, i)}
          />
        ) : (
          <StageGroupSection
            key={keyOf(sec, i)}
            group={sec}
            index={i + 1}
            chatState={chatState}
            expanded={isOpen(sec, i)}
            onToggle={() => toggle(sec, i)}
          />
        )
      )}
    </div>
  );
}

export default FlowStageSections;
