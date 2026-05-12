"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import { UrlBasedProvider, ProviderModelConfig } from "@/interfaces/llm";
import Card from "@/refresh-components/cards/Card";
import { ContentAction } from "@opal/layouts";
import { Button } from "@opal/components";
import { Section } from "@/layouts/general-layouts";
import { Hoverable } from "@opal/core";
import { SvgTrash, SvgDownload, SvgChevronDown, SvgChevronUp, SvgRefreshCw, SvgCheckCircle, SvgAlertCircle } from "@opal/icons";
import { getProviderIcon } from "@/lib/llmConfig/providers";

type TestStatus = "idle" | "testing" | "ok" | "error";

interface LiveModel {
  name: string;
  display_name?: string;
  size?: number;
  max_input_tokens?: number | null;
  supports_image_input?: boolean;
  supports_reasoning?: boolean;
}

interface Props {
  provider: UrlBasedProvider;
  onDownload?: (providerId: string) => void;
  /** When true, hides delete, download, and sync buttons (for built-in providers). */
  readOnly?: boolean;
}

const GROUP = (id: string) => `url-provider-${id}`;

function ModelLoadingSpinner() {
  return (
    <div className="flex items-center justify-center gap-2 px-3 py-4 text-sm text-muted-foreground">
      <SvgRefreshCw className="h-4 w-4 animate-spin" />
      <span>Loading models...</span>
    </div>
  );
}

function CapabilityBadges({ model }: { model: LiveModel | ProviderModelConfig }) {
  return (
    <span className="flex gap-1">
      {model.supports_image_input && (
        <span
          title="Supports image input"
          className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 font-medium"
        >
          Vision
        </span>
      )}
      {model.supports_reasoning && (
        <span
          title="Supports reasoning"
          className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 font-medium"
        >
          Reasoning
        </span>
      )}
    </span>
  );
}

export function UrlProviderCard({ provider, onDownload, readOnly = false }: Props) {
  const { mutate } = useSWRConfig();

  const [testStatus, setTestStatus] = useState<TestStatus>("idle");
  const [testLatency, setTestLatency] = useState<number | null>(null);

  const [expanded, setExpanded] = useState(false);
  const [liveModels, setLiveModels] = useState<LiveModel[] | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Prefer live-fetched model list; fall back to stored config
  const configModels = provider.config?.model_configurations ?? [];
  const displayModels: Array<LiveModel | ProviderModelConfig> =
    liveModels !== null ? liveModels : configModels;

  const handleTest = async () => {
    setTestStatus("testing");
    try {
      const res = await fetch("/api/admin/providers/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: provider.provider_type,
          base_url: provider.base_url,
        }),
      });
      const data = await res.json();
      setTestLatency(data.latency_ms ?? null);
      if (data.success) {
        setTestStatus("ok");
      } else {
        setTestStatus("error");
        toast({ message: data.error || "Connection failed", level: "error" });
      }
    } catch (e) {
      setTestStatus("error");
      toast({
        message: e instanceof Error ? e.message : "Connection failed",
        level: "error",
      });
    }
  };

  const handleToggleModels = async () => {
    if (expanded) {
      setExpanded(false);
      return;
    }
    // Show skeleton immediately before the fetch
    setModelsLoading(true);
    setExpanded(true);
    if (liveModels !== null) {
      setModelsLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/admin/providers/${provider.id}/models`);
      if (res.ok) {
        const data = await res.json();
        setLiveModels(Array.isArray(data) ? data : []);
      } else {
        setLiveModels([]);
      }
    } catch {
      setLiveModels([]);
    } finally {
      setModelsLoading(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await fetch(`/api/admin/providers/${provider.id}/sync-models`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Sync failed");
      const updated = await res.json();
      // Preserve size from previous live fetch (not stored in DB)
      const sizeMap = new Map((liveModels ?? []).map((m) => [m.name, m.size]));
      const synced: LiveModel[] = (updated?.config?.model_configurations ?? []).map(
        (m: ProviderModelConfig) => ({
          name: m.name,
          max_input_tokens: m.max_input_tokens,
          supports_image_input: m.supports_image_input,
          supports_reasoning: m.supports_reasoning,
          size: sizeMap.get(m.name),
        })
      );
      setLiveModels(synced);
      await mutate("/api/admin/providers");
      toast({ message: `Synced ${synced.length} model(s)` });
    } catch {
      toast({ message: "Failed to sync models", level: "error" });
    } finally {
      setSyncing(false);
    }
  };

  const handleDelete = async () => {
    try {
      await fetch(`/api/admin/providers/${provider.id}`, { method: "DELETE" });
      toast({ message: "Provider deleted" });
      mutate("/api/admin/providers");
    } catch {
      toast({ message: "Failed to delete provider", level: "error" });
    }
  };

  const syncButtonClass = [
    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors disabled:opacity-60",
    syncing
      ? "bg-muted text-foreground dark:bg-muted dark:text-foreground"
      : "text-muted-foreground hover:bg-muted hover:text-foreground",
  ].join(" ");

  return (
    <Hoverable.Root group={GROUP(provider.id)}>
      <Card padding={0.5}>
        <ContentAction
          icon={getProviderIcon(provider.provider_type)}
          title={provider.name}
          description={`${provider.base_url}${provider.user_config?.default_model ? ` · ${provider.user_config.default_model}` : ""}`}
          sizePreset="main-content"
          variant="section"
          rightChildren={
            <Section flexDirection="row" gap={0} alignItems="center">
              <Hoverable.Item group={GROUP(provider.id)} variant="opacity-on-hover">
                <button
                  type="button"
                  className={[
                    "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors disabled:opacity-50",
                    testStatus === "ok"
                      ? "text-green-600 bg-green-50 dark:bg-green-950/40 dark:text-green-400"
                      : testStatus === "error"
                      ? "text-red-600 bg-red-50 dark:bg-red-950/40 dark:text-red-400"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  ].join(" ")}
                  onClick={handleTest}
                  disabled={testStatus === "testing"}
                >
                  {testStatus === "ok" && <SvgCheckCircle className="h-4 w-4" />}
                  {testStatus === "error" && <SvgAlertCircle className="h-4 w-4" />}
                  <span>
                    {testStatus === "testing"
                      ? "Testing…"
                      : testStatus === "ok" && testLatency !== null
                      ? `${testLatency}ms`
                      : "Test"}
                  </span>
                </button>
              </Hoverable.Item>

              <Hoverable.Item group={GROUP(provider.id)} variant="opacity-on-hover">
                <Button
                  prominence="tertiary"
                  icon={expanded ? SvgChevronUp : SvgChevronDown}
                  onClick={handleToggleModels}
                />
              </Hoverable.Item>

              {!readOnly && provider.provider_type === "ollama" && onDownload && (
                <Hoverable.Item group={GROUP(provider.id)} variant="opacity-on-hover">
                  <Button
                    icon={SvgDownload}
                    prominence="tertiary"
                    onClick={() => onDownload(provider.id)}
                  />
                </Hoverable.Item>
              )}

              {!readOnly && (
                <Hoverable.Item group={GROUP(provider.id)} variant="opacity-on-hover">
                  <Button
                    icon={SvgTrash}
                    prominence="tertiary"
                    onClick={handleDelete}
                  />
                </Hoverable.Item>
              )}
            </Section>
          }
        />

        {expanded && (
          <div className="w-full mt-1 pt-2 border-t border-border">
            {modelsLoading ? (
              <ModelLoadingSpinner />
            ) : displayModels.length > 0 ? (
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center justify-between px-1 mb-1">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Models · {displayModels.length}
                  </p>
                  {!readOnly && (
                    <button
                      type="button"
                      className={syncButtonClass}
                      onClick={handleSync}
                      disabled={syncing}
                    >
                      <SvgRefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
                      <span>{syncing ? "Syncing..." : "Sync"}</span>
                    </button>
                  )}
                </div>
                {displayModels.map((m) => (
                  <div
                    key={m.name}
                    className="flex w-full items-center px-2 py-1.5 rounded-md hover:bg-muted transition-colors"
                  >
                    <span className="text-sm font-mono text-foreground truncate mr-2">
                      {"display_name" in m ? m.display_name || m.name : m.name}
                    </span>
                    <CapabilityBadges model={m} />
                    <span className="flex-1" />
                    {m.max_input_tokens != null && (
                      <span className="text-xs text-muted-foreground tabular-nums mr-3">
                        {m.max_input_tokens.toLocaleString()} ctx
                      </span>
                    )}
                    {"size" in m && m.size != null && m.size >= 5e7 && (
                      <span className="text-xs text-muted-foreground tabular-nums w-14 text-right">
                        {(m.size / 1e9).toFixed(1)} GB
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-between px-1 py-1">
                <p className="text-sm text-muted-foreground">No models found.</p>
                {!readOnly && (
                  <button
                    type="button"
                    className={syncButtonClass}
                    onClick={handleSync}
                    disabled={syncing}
                  >
                    <SvgRefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
                    <span>{syncing ? "Syncing..." : "Sync"}</span>
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </Card>
    </Hoverable.Root>
  );
}

