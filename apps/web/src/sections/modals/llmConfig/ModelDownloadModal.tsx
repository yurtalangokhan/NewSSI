"use client";

import { useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import Modal from "@/refresh-components/Modal";
import Message from "@/refresh-components/messages/Message";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";
import { cn, formatBytes } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
}

export interface OllamaProgress {
  status: string;
  digest?: string;
  completed?: number;
  total?: number;
  error?: string;
}

export interface ByteTotals {
  completed: number;
  total: number;
}

// Ollama streams one progress event per layer digest, each carrying only
// that layer's own byte counts — a fresh digest resets completed/total back
// to a small number, so showing the raw event's percentage makes the bar
// visibly jump backward between layers. Recording every digest seen so far
// and summing them gives one steadily-increasing overall percentage instead.
export function recordLayerProgress(
  layers: Map<string, ByteTotals>,
  event: OllamaProgress
): ByteTotals | null {
  if (!event.digest || !event.total) return null;
  layers.set(event.digest, {
    completed: event.completed ?? 0,
    total: event.total,
  });
  return sumLayers(layers);
}

// Ollama's /api/pull stream is newline-delimited SSE frames ("data: {...}").
// A frame carrying an "error" field (e.g. an unknown model name) is not an
// HTTP failure — the backend always appends a synthetic {"status":"done"}
// after it regardless — so callers must check every parsed frame for that
// field instead of trusting the stream reaching "done".
export function parseSseLine(line: string): OllamaProgress | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data:")) return null;
  const jsonStr = trimmed.slice(5).trim();
  try {
    return JSON.parse(jsonStr) as OllamaProgress;
  } catch {
    return null;
  }
}

export type PullErrorKind = "notFound" | "generic";

// Ollama's own error text ("pull model manifest: file does not exist",
// "model \"x\" not found, try pulling it first") isn't translated and isn't
// meant for end users, so we recognize the common "no such model" shape and
// swap in a localized message; anything else falls back to a translated
// wrapper around the raw text rather than showing it untranslated.
export function classifyPullError(rawError: string): PullErrorKind {
  const lower = rawError.toLowerCase();
  if (lower.includes("file does not exist") || lower.includes("not found")) {
    return "notFound";
  }
  return "generic";
}

function sumLayers(layers: Map<string, ByteTotals>): ByteTotals {
  let completed = 0;
  let total = 0;
  Array.from(layers.values()).forEach((layer) => {
    completed += layer.completed;
    total += layer.total;
  });
  return { completed, total };
}

function useAggregatePullProgress() {
  const layerBytesRef = useRef<Map<string, ByteTotals>>(new Map());
  const [aggregate, setAggregate] = useState<ByteTotals | null>(null);

  function record(event: OllamaProgress) {
    const next = recordLayerProgress(layerBytesRef.current, event);
    if (next) setAggregate(next);
  }

  function reset() {
    layerBytesRef.current.clear();
    setAggregate(null);
  }

  return { aggregate, record, reset };
}

export function ModelDownloadModal({ open, onOpenChange, providerId }: Props) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();

  function friendlyStatus(status: string | undefined): string {
    if (!status) return "";
    if (status.includes("pulling manifest")) {
      return t("admin.llm.pullPullingManifest", "Pulling manifest…");
    }
    if (status.includes("verifying")) {
      return t("admin.llm.pullVerifying", "Verifying digest…");
    }
    if (status.includes("writing manifest")) {
      return t("admin.llm.pullWritingManifest", "Writing manifest…");
    }
    if (status.includes("removing")) {
      return t("admin.llm.pullCleaningUp", "Cleaning up…");
    }
    if (status === "success" || status === "done") {
      return t("admin.llm.pullSuccess", "Download complete");
    }
    if (status.startsWith("pulling ")) {
      return t("admin.llm.pullDownloadingLayer", "Downloading…");
    }
    return status;
  }

  function friendlyPullError(rawError: string): string {
    if (classifyPullError(rawError) === "notFound") {
      return t("admin.llm.pullModelNotFound", {
        model: modelName,
        defaultValue: 'Model "{{model}}" not found.',
      });
    }
    return t("admin.llm.pullErrorGeneric", {
      message: rawError,
      defaultValue: "Download failed: {{message}}",
    });
  }

  const [modelName, setModelName] = useState("");
  const [pulling, setPulling] = useState(false);
  const [progress, setProgress] = useState<OllamaProgress | null>(null);
  const [done, setDone] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(
    null
  );
  const {
    aggregate,
    record,
    reset: resetAggregate,
  } = useAggregatePullProgress();

  const reset = () => {
    setModelName("");
    setPulling(false);
    setProgress(null);
    setDone(false);
    setErrorMessage(null);
    resetAggregate();
  };

  const handleClose = () => {
    readerRef.current?.cancel();
    reset();
    onOpenChange(false);
  };

  const handlePull = async () => {
    if (!modelName.trim()) {
      toast({ message: t("admin.llm.modelNameRequired"), level: "error" });
      return;
    }
    setPulling(true);
    setDone(false);
    setErrorMessage(null);
    resetAggregate();
    setProgress({ status: t("admin.llm.starting") });

    try {
      const res = await fetch("/api/admin/ollama/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: modelName.trim(),
          provider_id: providerId,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(t("admin.llm.pullRequestFailed"));
      }

      const reader = res.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = "";
      let pullError: string | undefined;

      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const parsed = parseSseLine(line);
          if (!parsed) continue;
          if (parsed.error) {
            pullError = parsed.error;
            continue;
          }
          setProgress(parsed);
          record(parsed);
        }
      }

      if (pullError) {
        setProgress(null);
        resetAggregate();
        const friendly = friendlyPullError(pullError);
        setErrorMessage(friendly);
        toast({ message: friendly, level: "error" });
        return;
      }

      setDone(true);
      toast({ message: t("admin.llm.modelDownloaded", { model: modelName }) });
      await mutate(`/api/admin/providers/${providerId}/models`);
      await mutate("/api/admin/ollama/models");
      await mutate("/api/admin/ollama/status");
    } catch (e: unknown) {
      setProgress(null);
      resetAggregate();
      const message =
        e instanceof Error ? e.message : t("admin.llm.pullFailed");
      setErrorMessage(message);
      toast({ message, level: "error" });
    } finally {
      setPulling(false);
    }
  };

  const pct = aggregate?.total
    ? Math.round((aggregate.completed / aggregate.total) * 100)
    : null;

  return (
    <Modal open={open} onOpenChange={handleClose}>
      <Modal.Content width="sm">
        <Modal.Header
          title={t("admin.llm.downloadOllamaModel")}
          onClose={handleClose}
        />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.modelName")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={t("admin.llm.modelNameExample")}
                value={modelName}
                disabled={pulling || done}
                onChange={(e) => {
                  setModelName(e.target.value);
                  setErrorMessage(null);
                }}
              />
            </div>

            {errorMessage && (
              <Message
                error
                close={false}
                text={errorMessage}
                className="w-full"
              />
            )}

            {progress && (
              <div className="space-y-1.5">
                <div className="flex justify-between items-center gap-2">
                  <Text secondaryBody>{friendlyStatus(progress.status)}</Text>
                  {pct !== null && (
                    <Text secondaryBody text03>
                      {t("admin.llm.pullPercentLabel", {
                        percent: pct,
                        defaultValue: "{{percent}}%",
                      })}
                      {aggregate &&
                        ` · ${formatBytes(aggregate.completed)} / ${formatBytes(
                          aggregate.total
                        )}`}
                    </Text>
                  )}
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full rounded-full bg-primary",
                      pct !== null ? "transition-all" : "w-full animate-pulse"
                    )}
                    style={pct !== null ? { width: `${pct}%` } : undefined}
                  />
                </div>
              </div>
            )}
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Button
            prominence="secondary"
            onClick={handleClose}
            disabled={pulling && !done}
          >
            {done ? t("modals.done") : t("modals.cancel")}
          </Button>
          {!done && (
            <Button
              prominence="primary"
              onClick={handlePull}
              disabled={pulling}
            >
              {pulling ? t("admin.llm.downloading") : t("admin.llm.download")}
            </Button>
          )}
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
