"use client";

import { useState, useRef } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { useTranslation } from "react-i18next";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  providerId: string;
}

interface OllamaProgress {
  status: string;
  completed?: number;
  total?: number;
}

export function ModelDownloadModal({ open, onOpenChange, providerId }: Props) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();
  const [modelName, setModelName] = useState("");
  const [pulling, setPulling] = useState(false);
  const [progress, setProgress] = useState<OllamaProgress | null>(null);
  const [done, setDone] = useState(false);
  const readerRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);

  const reset = () => {
    setModelName("");
    setPulling(false);
    setProgress(null);
    setDone(false);
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
    setProgress({ status: t("admin.llm.starting") });

    try {
      const res = await fetch("/api/admin/ollama/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelName.trim(), provider_id: providerId }),
      });

      if (!res.ok || !res.body) {
        throw new Error(t("admin.llm.pullRequestFailed"));
      }

      const reader = res.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const jsonStr = trimmed.slice(5).trim();
          try {
            const parsed: OllamaProgress = JSON.parse(jsonStr);
            setProgress(parsed);
            if (parsed.status === "done") {
              setDone(true);
            }
          } catch {
            // ignore malformed lines
          }
        }
      }

      setDone(true);
      toast({ message: t("admin.llm.modelDownloaded", { model: modelName }) });
      await mutate(`/api/admin/providers/${providerId}/models`);
      await mutate("/api/admin/ollama/models");
      await mutate("/api/admin/ollama/status");
    } catch (e: unknown) {
      toast({
        message: e instanceof Error ? e.message : t("admin.llm.pullFailed"),
        level: "error",
      });
    } finally {
      setPulling(false);
    }
  };

  const pct =
    progress?.total && progress.completed
      ? Math.round((progress.completed / progress.total) * 100)
      : null;

  return (
    <Modal open={open} onOpenChange={handleClose}>
      <Modal.Content width="sm">
        <Modal.Header title={t("admin.llm.downloadOllamaModel")} onClose={handleClose} />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.modelName")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={t("admin.llm.modelNameExample")}
                value={modelName}
                disabled={pulling}
                onChange={(e) => setModelName(e.target.value)}
              />
            </div>

            {progress && (
              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <Text secondaryBody>{progress.status}</Text>
                </div>
                {pct !== null && (
                  <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Button prominence="secondary" onClick={handleClose} disabled={pulling && !done}>
            {done ? t("modals.done") : t("modals.cancel")}
          </Button>
          {!done && (
            <Button prominence="primary" onClick={handlePull} disabled={pulling}>
              {pulling ? t("admin.llm.downloading") : t("admin.llm.download")}
            </Button>
          )}
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
