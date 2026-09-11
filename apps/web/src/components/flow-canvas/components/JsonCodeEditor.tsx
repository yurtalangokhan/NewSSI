"use client";

import React, { useMemo, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import hljs from "highlight.js/lib/core";
import jsonLanguage from "highlight.js/lib/languages/json";
import { cn } from "@/lib/utils";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import {
  SvgCheck,
  SvgCopy,
  SvgTrash,
  SvgXCircle,
  SvgCheckCircle,
  SvgSparkle,
} from "@opal/icons";

// Register JSON language once
if (!hljs.getLanguage("json")) {
  hljs.registerLanguage("json", jsonLanguage);
}

export interface JsonCodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  errorDetails?: {
    message: string;
    line?: number;
    column?: number;
  } | null;
  isValidFlow?: boolean;
  validStats?: {
    nodeCount: number;
    edgeCount: number;
  } | null;
  onLoadSample?: () => void;
  className?: string;
  height?: string;
}

export function JsonCodeEditor({
  value,
  onChange,
  placeholder,
  readOnly = false,
  errorDetails,
  isValidFlow,
  validStats,
  onLoadSample,
  className,
  height = "340px",
}: JsonCodeEditorProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);

  // Synchronize scroll between textarea, pre (highlighted code), and line numbers gutter
  const handleScroll = useCallback(() => {
    if (!textareaRef.current) return;
    const { scrollTop, scrollLeft } = textareaRef.current;
    if (preRef.current) {
      preRef.current.scrollTop = scrollTop;
      preRef.current.scrollLeft = scrollLeft;
    }
    if (gutterRef.current) {
      gutterRef.current.scrollTop = scrollTop;
    }
  }, []);

  // Compute line count
  const lines = useMemo(() => {
    if (!value) return [1];
    const split = value.split("\n");
    return Array.from({ length: split.length }, (_, i) => i + 1);
  }, [value]);

  // Syntax highlighting for JSON
  const highlightedHtml = useMemo(() => {
    if (!value) return "";
    try {
      return hljs.highlight(value, { language: "json" }).value;
    } catch {
      return value
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }
  }, [value]);

  // Tab key handler: insert 2 spaces instead of moving focus
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const textarea = e.currentTarget;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const spaces = "  ";

      const nextValue =
        value.substring(0, start) + spaces + value.substring(end);
      onChange(nextValue);

      // Restore cursor position after inserted spaces
      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = start + spaces.length;
          textareaRef.current.selectionEnd = start + spaces.length;
        }
      });
    }
  };

  // Format JSON action (Pretty-Print)
  const handleFormat = () => {
    if (!value.trim()) return;
    try {
      const parsed = JSON.parse(value);
      const formatted = JSON.stringify(parsed, null, 2);
      onChange(formatted);
    } catch {
      // If parsing fails, no formatting is possible
    }
  };

  // Copy to clipboard action
  const handleCopy = async () => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback or ignore
    }
  };

  // Clear action
  const handleClear = () => {
    onChange("");
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  const isFormattable = useMemo(() => {
    if (!value.trim()) return false;
    try {
      JSON.parse(value);
      return true;
    } catch {
      return false;
    }
  }, [value]);

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-border-01 bg-background-tint-00 shadow-xs overflow-hidden",
        className
      )}
    >
      {/* Editor Header Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-01 bg-background-tint-01 text-xs">
        {/* Left: Validation Status Badge */}
        <div className="flex items-center gap-2 min-w-0">
          {!value.trim() ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-medium text-[11px] bg-background-neutral-01 text-text-03 border border-border-01">
              {t("flowCanvas.noContent", "Henüz JSON girilmedi")}
            </span>
          ) : errorDetails ? (
            <span
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-medium text-[11px] bg-theme-red-01 text-theme-red-05 border border-theme-red-02 truncate"
              title={errorDetails.message}
            >
              <SvgXCircle className="w-3.5 h-3.5 shrink-0 text-theme-red-05" />
              <span className="truncate">
                {errorDetails.line
                  ? `${t("flowCanvas.invalidJson", "Geçersiz JSON")}: ${t(
                      "lines_one",
                      { count: errorDetails.line }
                    )}`
                  : errorDetails.message}
              </span>
            </span>
          ) : isValidFlow && validStats ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-medium text-[11px] bg-theme-green-01 text-theme-green-05 border border-theme-green-02">
              <SvgCheckCircle className="w-3.5 h-3.5 shrink-0 text-theme-green-05" />
              <span>
                {t(
                  "flowCanvas.validFlow",
                  "Geçerli Akış ({{nodes}} düğüm, {{edges}} bağlantı)",
                  { nodes: validStats.nodeCount, edges: validStats.edgeCount }
                )}
              </span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md font-medium text-[11px] bg-theme-amber-01 text-theme-amber-05 border border-theme-amber-02">
              <SvgXCircle className="w-3.5 h-3.5 shrink-0 text-theme-amber-05" />
              <span>{t("flowCanvas.invalidFlow", "Geçersiz Akış Yapısı")}</span>
            </span>
          )}
        </div>

        {/* Right: Quick Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {onLoadSample && (
            <Button
              tertiary
              size="md"
              leftIcon={SvgSparkle}
              onClick={onLoadSample}
              title={t("flowCanvas.loadSample", "Örnek Şablon")}
            >
              {t("flowCanvas.loadSample", "Örnek Şablon")}
            </Button>
          )}
          <Button
            tertiary
            size="md"
            onClick={handleFormat}
            disabled={!isFormattable}
            title={t("flowCanvas.formatJson", "Biçimlendir")}
          >
            {t("flowCanvas.formatJson", "Biçimlendir")}
          </Button>
          <Button
            tertiary
            size="md"
            leftIcon={copied ? SvgCheck : SvgCopy}
            onClick={handleCopy}
            disabled={!value.trim()}
            title={
              copied
                ? t("flowCanvas.copied", "Kopyalandı!")
                : t("flowCanvas.copyJson", "Kopyala")
            }
          >
            {copied
              ? t("flowCanvas.copied", "Kopyalandı!")
              : t("flowCanvas.copyJson", "Kopyala")}
          </Button>
          <IconButton
            tertiary
            small
            icon={SvgTrash}
            onClick={handleClear}
            disabled={!value.trim() || readOnly}
            tooltip={t("flowCanvas.clearJson", "Temizle")}
            aria-label={t("flowCanvas.clearJson", "Temizle")}
          />
        </div>
      </div>

      {/* Code Editor Body (Gutter + Highlighted text area) */}
      <div
        className="relative flex w-full font-mono text-[13px] leading-[22px] bg-background-neutral-00"
        style={{ height }}
      >
        {/* Line Numbers Gutter */}
        <div
          ref={gutterRef}
          aria-hidden="true"
          className="shrink-0 select-none overflow-hidden py-3 px-2 text-right text-text-03 bg-background-tint-01/60 border-r border-border-01 min-w-[3rem]"
        >
          {lines.map((lineNum) => {
            const isErrorLine = errorDetails?.line === lineNum;
            return (
              <div
                key={lineNum}
                className={cn(
                  "h-[22px] px-1 rounded-sm transition-colors",
                  isErrorLine
                    ? "bg-theme-red-01 text-theme-red-05 font-bold"
                    : ""
                )}
              >
                {lineNum}
              </div>
            );
          })}
        </div>

        {/* Editor Container with Layered Highlight + Textarea */}
        <div className="relative flex-1 h-full overflow-hidden">
          {/* Syntax Highlighted Layer (Background) */}
          <pre
            ref={preRef}
            aria-hidden="true"
            className="hljs absolute inset-0 m-0 p-3 overflow-auto whitespace-pre font-mono text-[13px] leading-[22px] pointer-events-none select-none bg-transparent border-none"
            dangerouslySetInnerHTML={{
              __html:
                highlightedHtml ||
                (placeholder && !value
                  ? `<span class="text-text-03">${placeholder}</span>`
                  : "&nbsp;"),
            }}
          />

          {/* Interactive Textarea (Foreground) */}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onScroll={handleScroll}
            onKeyDown={handleKeyDown}
            readOnly={readOnly}
            placeholder={
              placeholder ||
              t(
                "flowCanvas.editorPlaceholder",
                "Flow JSON verisini buraya yapıştırın veya yazın..."
              )
            }
            spellCheck={false}
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
            data-testid="json-code-editor-textarea"
            className={cn(
              "absolute inset-0 w-full h-full m-0 p-3 resize-none font-mono text-[13px] leading-[22px] whitespace-pre",
              "bg-transparent outline-none border-none",
              "text-transparent caret-text-04",
              "selection:bg-action-link-01 selection:text-transparent",
              "overflow-auto"
            )}
          />
        </div>
      </div>

      {/* Bottom Error Banner if syntax is invalid */}
      {errorDetails && (
        <div
          data-testid="json-editor-error-banner"
          className="flex items-start gap-2.5 px-3.5 py-2.5 bg-theme-red-01 border-t border-theme-red-02 text-theme-red-05 text-xs font-mono"
        >
          <SvgXCircle className="w-4 h-4 shrink-0 mt-0.5 text-theme-red-05" />
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="font-semibold text-[11px] uppercase tracking-wider text-theme-red-05">
              {t("flowCanvas.invalidJson", "JSON Sözdizimi Hatası")}
              {errorDetails.line &&
                ` (${t("lines_one", { count: errorDetails.line })}${
                  errorDetails.column ? `, sütun ${errorDetails.column}` : ""
                })`}
            </span>
            <span className="break-all text-xs opacity-90">
              {errorDetails.message}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default JsonCodeEditor;
