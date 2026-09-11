/**
 * Playground panel UI for testing draft flows.
 *
 * Spec: .tmp/flow-canvas-design.md section 6 (in full).
 * Brief: .tmp/flow-canvas-task-44-brief.md
 */

import { ChangeEvent, FormEvent, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  SvgCheck,
  SvgChevronDown,
  SvgChevronRight,
  SvgClock,
  SvgCopy,
  SvgLoader,
  SvgPaperclip,
  SvgPlayCircle,
  SvgRefreshCw,
  SvgTerminal,
  SvgTrash,
  SvgX,
} from "@opal/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import Text from "@/refresh-components/texts/Text";
import type { StoreApi } from "zustand";
import type { FlowStore } from "../stores/flowStore";
import {
  usePlaygroundRun,
  type PlaygroundToolCall,
} from "../hooks/usePlaygroundRun";
import { formatDuration, formatTokenCount } from "../utils/formatStats";

/** Best-effort pretty-print of a tool call's arguments / output for the
 * collapsible block — strings pass through, everything else is indented JSON. */
function prettyValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Langflow-style tool-call block: name header + collapsible Arguments /
 * Output. Expanded while the call is still running, collapsible afterwards
 * — same interaction as `ReasoningBlock`. */
function ToolCallBlock({ toolCall }: { toolCall: PlaygroundToolCall }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const running = toolCall.status === "running";
  const showContent = running || expanded;
  const Chevron = showContent ? SvgChevronDown : SvgChevronRight;

  return (
    <div className="mb-1 w-full max-w-[85%]" data-testid="playground-tool-call">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-canvas-fg"
        data-testid="playground-tool-call-toggle"
      >
        <Chevron className="h-3 w-3 shrink-0" />
        <SvgTerminal className="h-3 w-3 shrink-0" />
        <span className="font-medium uppercase tracking-wide">
          {toolCall.name}
        </span>
        {running ? (
          <SvgLoader className="h-3 w-3 shrink-0 animate-spin" />
        ) : (
          <SvgCheck className="h-3 w-3 shrink-0 text-theme-green-05" />
        )}
      </button>
      {showContent && (
        <div
          className="mt-1 space-y-2 rounded-md border border-canvas-border bg-muted/50 p-2 text-xs text-muted-foreground"
          data-testid="playground-tool-call-content"
        >
          <div>
            <div className="mb-1 font-semibold">
              {t("flowCanvas.playground.toolArguments", "Arguments")}
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap break-words">
              {prettyValue(toolCall.input)}
            </pre>
          </div>
          {toolCall.output !== undefined && (
            <div>
              <div className="mb-1 font-semibold">
                {t("flowCanvas.playground.toolOutput", "Output")}
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap break-words">
                {prettyValue(toolCall.output)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Scope: text-based attachments only (PDF/docx/pptx/xlsx/csv/txt/md) — no
 * images this round, so the picker doesn't advertise vision support the
 * flow side doesn't specifically handle yet. Matches
 * `service/FileService.py`'s own document parsers. */
const PLAYGROUND_FILE_ACCEPT = [
  "application/pdf",
  ".docx",
  ".doc",
  ".pptx",
  ".ppt",
  "text/csv",
  ".csv",
  ".xlsx",
  ".xls",
  "text/plain",
  ".txt",
  ".md",
].join(",");

/** Live while streaming (isThinking), collapsible afterwards — mirrors the
 * main chat's "Thinking…" block (ReasoningRenderer.tsx) at a scale that
 * fits this panel: no modal/copy/download, just expand-in-place. */
function ReasoningBlock({
  reasoning,
  isThinking,
}: {
  reasoning: string;
  isThinking?: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const showContent = isThinking || expanded;
  const Chevron = showContent ? SvgChevronDown : SvgChevronRight;

  return (
    <div className="mb-1 w-full max-w-[85%]" data-testid="playground-reasoning">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-canvas-fg"
        data-testid="playground-reasoning-toggle"
      >
        <Chevron className="h-3 w-3" />
        {isThinking
          ? t("flowCanvas.playground.thinkingActive", "Thinking…")
          : t("flowCanvas.playground.thinking", "Thinking")}
      </button>
      {showContent && (
        <div
          className="mt-1 whitespace-pre-wrap rounded-md border border-canvas-border bg-muted/50 p-2 text-xs text-muted-foreground"
          data-testid="playground-reasoning-content"
        >
          {reasoning}
        </div>
      )}
    </div>
  );
}

export type PlaygroundPanelProps = {
  /** `null` for a flow that has never been saved yet — the current canvas
   * graph is run inline instead of a persisted draft. */
  definitionId: string | null;
  open: boolean;
  onClose: () => void;
  store?: StoreApi<FlowStore>;
};

export function PlaygroundPanel({
  definitionId,
  open,
  onClose,
  store,
}: PlaygroundPanelProps) {
  const { t } = useTranslation();
  const { messages, isRunning, error, send, retry, clear } = usePlaygroundRun(
    definitionId,
    store
  );
  const [inputText, setInputText] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const handleCopy = async (index: number, text: string) => {
    try {
      await navigator.clipboard?.writeText(text);
      setCopiedIndex(index);
      setTimeout(
        () => setCopiedIndex((cur) => (cur === index ? null : cur)),
        1500
      );
    } catch {
      // Clipboard unavailable (insecure context / denied) — nothing to do.
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    // The canvas this panel is embedded in (InlineFlowDesigner) sits inside
    // the create-agent Formik <form> — 'submit' bubbles regardless of
    // preventDefault, so without this an unrelated ancestor form's
    // onSubmit fires too and navigates the whole page away.
    e.stopPropagation();
    if ((!inputText.trim() && attachedFiles.length === 0) || isRunning) return;
    const text = inputText;
    const files = attachedFiles;
    setInputText("");
    setAttachedFiles([]);
    await send(text, files);
  };

  const handleFilesPicked = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(e.target.files ?? []);
    if (picked.length > 0) setAttachedFiles((prev) => [...prev, ...picked]);
    e.target.value = "";
  };

  const removeAttachedFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div
      className="absolute inset-y-0 right-0 z-20 flex w-96 flex-col border-l border-canvas-border bg-canvas-panel shadow-2xl transition-transform duration-200"
      data-testid="playground-panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-canvas-border px-4 py-3">
        <div className="flex items-center gap-2">
          <SvgPlayCircle className="h-5 w-5 text-primary" />
          <Text mainUiBody className="font-semibold">
            {t("flowCanvas.playground.title", "Flow Playground")}
          </Text>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <IconButton
              icon={SvgTrash}
              tooltip={t("flowCanvas.playground.clearChat", "Clear chat")}
              aria-label={t("flowCanvas.playground.clearChat", "Clear chat")}
              onClick={clear}
              data-testid="playground-clear"
            />
          )}
          <IconButton
            icon={SvgX}
            tooltip={t("flowCanvas.playground.close", "Close playground")}
            aria-label={t("flowCanvas.playground.close", "Close playground")}
            onClick={onClose}
            data-testid="playground-close"
          />
        </div>
      </div>

      {/* Draft Mode Banner (§5.2) */}
      <div
        className="flex items-center gap-2 border-b border-theme-amber-02 bg-theme-amber-01 px-4 py-2 text-xs text-theme-amber-05"
        data-testid="playground-draft-banner"
      >
        <span className="h-2 w-2 rounded-full bg-theme-amber-02" />
        <Text text03 secondaryBody className="text-inherit">
          {definitionId === null
            ? t(
                "flowCanvas.playground.draftBannerNew",
                "Playground — testing your unsaved flow, nothing is stored"
              )
            : t(
                "flowCanvas.playground.draftBannerDraft",
                "Playground — running your draft, not the published version"
              )}
        </Text>
      </div>

      {/* Transcript */}
      <div
        className="flex flex-1 flex-col gap-3 overflow-y-auto p-4"
        data-testid="playground-messages"
      >
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
            <Text secondaryBody text03>
              {t(
                "flowCanvas.playground.emptyState",
                "Send a message to test this flow in real time."
              )}
            </Text>
          </div>
        )}

        {messages.map((msg, index) => {
          const isUser = msg.role === "user";
          const isLastMessage = index === messages.length - 1;
          const itemClass =
            "group/msg flex flex-col " + (isUser ? "items-end" : "items-start");
          const boxClass =
            "max-w-[85%] rounded-lg px-3 py-2 text-sm " +
            (isUser
              ? "bg-primary text-primary-foreground"
              : msg.isError
                ? "border border-destructive/30 bg-destructive/15 text-destructive"
                : "bg-muted text-canvas-fg");
          const tokenLabel = msg.usage
            ? formatTokenCount(msg.usage.totalTokens)
            : null;
          const durationLabel =
            msg.durationMs != null ? formatDuration(msg.durationMs) : null;
          const usageTitle = msg.usage
            ? `${t("flowCanvas.playground.tokensInputLabel", "Input")} ${
                msg.usage.inputTokens
              } · ` +
              `${t("flowCanvas.playground.tokensOutputLabel", "Output")} ${
                msg.usage.outputTokens
              } · ` +
              `${t("flowCanvas.playground.tokensTotalLabel", "Total")} ${
                msg.usage.totalTokens
              }`
            : undefined;
          // The trailing assistant turn is still streaming while `isRunning`
          // — its actions only make sense once it has settled.
          const turnSettled =
            !isUser && !msg.isError && (!isLastMessage || !isRunning);
          const canCopy = turnSettled && msg.content.trim().length > 0;
          const canRetry = turnSettled && isLastMessage;
          const showFooter = Boolean(
            tokenLabel || durationLabel || canCopy || canRetry
          );
          return (
            <div
              key={index}
              className={itemClass}
              data-testid={"playground-message-" + msg.role}
            >
              {!isUser && msg.reasoning && (
                <ReasoningBlock
                  reasoning={msg.reasoning}
                  isThinking={msg.isThinking}
                />
              )}
              {!isUser &&
                msg.toolCalls?.map((toolCall) => (
                  <ToolCallBlock key={toolCall.callId} toolCall={toolCall} />
                ))}
              {isUser &&
                msg.attachedFileNames &&
                msg.attachedFileNames.length > 0 && (
                  <div className="mb-1 flex max-w-[85%] flex-wrap justify-end gap-1">
                    {msg.attachedFileNames.map((name, fileIndex) => (
                      <span
                        key={fileIndex}
                        className="flex items-center gap-1 rounded-md border border-canvas-border bg-muted px-2 py-1 text-xs text-muted-foreground"
                      >
                        <SvgPaperclip className="h-3 w-3 shrink-0" />
                        <span className="max-w-[10rem] truncate">{name}</span>
                      </span>
                    ))}
                  </div>
                )}
              <div className={boxClass}>
                <div className="whitespace-pre-wrap">
                  {msg.content ||
                    (isRunning &&
                    msg.role === "assistant" &&
                    !msg.isThinking &&
                    !msg.reasoning
                      ? "…"
                      : "")}
                </div>
              </div>

              {!isUser && showFooter && (
                <div className="mt-1 flex h-6 items-center gap-2 text-[11px] text-muted-foreground">
                  {(durationLabel || tokenLabel) && (
                    <div
                      className="flex items-center gap-2"
                      data-testid="playground-message-stats"
                      title={usageTitle}
                    >
                      {durationLabel && (
                        <span className="flex items-center gap-1">
                          <SvgClock className="h-3 w-3 shrink-0" />
                          {durationLabel}
                        </span>
                      )}
                      {tokenLabel && (
                        <span>
                          {tokenLabel}{" "}
                          {t("flowCanvas.playground.tokens", "tokens")}
                        </span>
                      )}
                    </div>
                  )}
                  {(canCopy || canRetry) && (
                    <div className="flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/msg:opacity-100">
                      {canCopy && (
                        <IconButton
                          internal
                          small
                          icon={copiedIndex === index ? SvgCheck : SvgCopy}
                          tooltip={
                            copiedIndex === index
                              ? t("flowCanvas.playground.copied", "Copied")
                              : t("flowCanvas.playground.copy", "Copy")
                          }
                          tooltipSize="sm"
                          aria-label={t("flowCanvas.playground.copy", "Copy")}
                          onClick={() => handleCopy(index, msg.content)}
                          data-testid="playground-copy"
                        />
                      )}
                      {canRetry && (
                        <IconButton
                          internal
                          small
                          icon={SvgRefreshCw}
                          tooltip={t("flowCanvas.playground.retry", "Retry")}
                          tooltipSize="sm"
                          aria-label={t("flowCanvas.playground.retry", "Retry")}
                          onClick={() => retry()}
                          data-testid="playground-retry"
                        />
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {error && (
          <div
            className="rounded border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive"
            data-testid="playground-error"
          >
            {error}
          </div>
        )}
      </div>

      {/* Input form */}
      <form
        onSubmit={handleSubmit}
        className="w-full border-t border-canvas-border p-3"
      >
        {attachedFiles.length > 0 && (
          <div
            className="mb-2 flex flex-wrap gap-1"
            data-testid="playground-attached-files"
          >
            {attachedFiles.map((file, index) => (
              <span
                key={index}
                className="flex items-center gap-1 rounded-md border border-canvas-border bg-muted px-2 py-1 text-xs text-canvas-fg"
              >
                <SvgPaperclip className="h-3 w-3 shrink-0" />
                <span className="max-w-[8rem] truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachedFile(index)}
                  aria-label={t(
                    "flowCanvas.playground.removeAttachment",
                    "Remove attachment"
                  )}
                  className="text-muted-foreground hover:text-canvas-fg"
                >
                  <SvgX className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="flex w-full items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={PLAYGROUND_FILE_ACCEPT}
            onChange={handleFilesPicked}
            className="hidden"
            data-testid="playground-file-input"
          />
          <IconButton
            icon={SvgPaperclip}
            tooltip={t("flowCanvas.playground.attachFile", "Attach a file")}
            aria-label={t("flowCanvas.playground.attachFile", "Attach a file")}
            disabled={isRunning}
            onClick={() => fileInputRef.current?.click()}
            data-testid="playground-attach"
          />
          <input
            type="text"
            value={inputText}
            onChange={(evt) => setInputText(evt.target.value)}
            placeholder={t(
              "flowCanvas.playground.placeholder",
              "Type a message…"
            )}
            disabled={isRunning}
            data-testid="playground-input"
            className="w-full min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button
            main
            type="submit"
            disabled={
              (!inputText.trim() && attachedFiles.length === 0) || isRunning
            }
            data-testid="playground-send"
            className="shrink-0"
          >
            {t("flowCanvas.playground.send", "Send")}
          </Button>
        </div>
      </form>
    </div>
  );
}
