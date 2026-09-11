import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { StoreApi } from "zustand";
import { fileToBase64 } from "@/lib/multimodal-utils";
import { flowApi } from "@/components/flow-canvas/api/flowApi";
import type { FlowStore } from "../stores/flowStore";
import { toFlowSpec } from "../utils/compile";

/** One tool invocation within a run — the raw material for the playground's
 * Langflow-style collapsible tool-call block. `callId` correlates the
 * `tool_call_start` / `tool_call_end` SSE pair. */
export type PlaygroundToolCall = {
  callId: string;
  name: string;
  input?: unknown;
  output?: unknown;
  status: "running" | "done";
};

export type PlaygroundMessage = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  isError?: boolean;
  /** Reasoning-capable models stream "thinking" text separately from the
   * final answer — accumulated here so the UI can show it as its own
   * collapsible block, same as the main chat. */
  reasoning?: string;
  /** True from the first reasoning_delta until reasoning_done arrives. */
  isThinking?: boolean;
  /** Names of files attached to this turn (display only — the actual
   * content already went to the backend as part of the request). */
  attachedFileNames?: string[];
  /** Tool calls made while producing this assistant turn (playground only). */
  toolCalls?: PlaygroundToolCall[];
  /** Cumulative token usage for the run, from the last `usage` SSE event. */
  usage?: { inputTokens: number; outputTokens: number; totalTokens: number };
  /** Total wall-clock duration of the run in ms, from the `run_end` event. */
  durationMs?: number;
};

/** FastAPI's `detail` is a string for most 4xx/5xx errors, but the flow
 * validator (FLOW_NO_EXIT etc.) returns `{errors: [{message, ...}]}`
 * instead — `String(detail)` on that object produces the literal text
 * "[object Object]", which is what a user actually saw. */
function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (
    detail &&
    typeof detail === "object" &&
    Array.isArray((detail as { errors?: unknown }).errors)
  ) {
    const messages = (detail as { errors: Array<{ message?: string }> }).errors
      .map((issue) => issue.message)
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return messages.join("; ");
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export type UsePlaygroundRunReturn = {
  messages: PlaygroundMessage[];
  isRunning: boolean;
  error: string | null;
  send: (text: string, files?: File[]) => Promise<void>;
  retry: () => Promise<void>;
  clear: () => void;
};

/**
 * @param definitionId The saved flow's id, or `null` for a flow that has
 * never been saved yet (e.g. still on the "create agent" form) — in that
 * case `store`'s current graph is sent inline on every run instead of being
 * looked up by id, matching Langflow's own build endpoint.
 */
export function usePlaygroundRun(
  definitionId: string | null,
  store?: StoreApi<FlowStore>
): UsePlaygroundRunReturn {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<PlaygroundMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Mirror of `messages` for synchronous reads (retry needs the current
  // transcript before the next render flushes a functional update).
  const messagesRef = useRef<PlaygroundMessage[]>([]);
  messagesRef.current = messages;
  const activeDefIdRef = useRef(definitionId);
  const sessionIdRef = useRef<string | null>(null);
  if (definitionId === null && sessionIdRef.current === null) {
    sessionIdRef.current =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
  }

  useEffect(() => {
    if (activeDefIdRef.current !== definitionId) {
      activeDefIdRef.current = definitionId;
      setMessages([]);
      setError(null);
      setIsRunning(false);
      store?.getState().resetNodeRunStatus();
    }
  }, [definitionId, store]);

  const clear = useCallback(() => {
    setMessages([]);
    setError(null);
    store?.getState().resetNodeRunStatus();
  }, [store]);

  /** Mutate the trailing assistant message. */
  const patchAssistant = useCallback(
    (patch: (msg: PlaygroundMessage) => PlaygroundMessage) => {
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        const lastMsg = updated[lastIdx];
        if (lastIdx >= 0 && lastMsg && lastMsg.role === "assistant") {
          updated[lastIdx] = patch(lastMsg);
        }
        return updated;
      });
    },
    []
  );

  /** Fetch + parse the SSE stream for a turn whose user message and an
   * empty trailing assistant message are already in `messages`. Shared by
   * `send` and `retry`. */
  const runStream = useCallback(
    async (text: string, attachments: File[]) => {
      const trimmed = text.trim();
      try {
        // Files travel inline as base64 content blocks on the user message
        // — no separate upload endpoint, mirroring the main chat's own
        // file_descriptors pattern (multimodal-utils.ts) and consumed by
        // the same shared `convert_input_messages`/`_extract_file_blocks`
        // backend path (service/utils.py) that already turns a "file"
        // block into extracted text folded into the turn's HumanMessage.
        const fileBlocks =
          attachments.length > 0
            ? await Promise.all(
                attachments.map(async (file) => ({
                  type: "file" as const,
                  mime_type: file.type || "application/octet-stream",
                  data: await fileToBase64(file),
                  metadata: { filename: file.name },
                }))
              )
            : [];

        const url = flowApi.playgroundStream(definitionId ?? undefined);
        const messagePayload =
          fileBlocks.length > 0
            ? {
                input: {
                  messages: [
                    {
                      role: "user",
                      content: [{ type: "text", text: trimmed }, ...fileBlocks],
                    },
                  ],
                },
              }
            : { message: trimmed };
        const body =
          definitionId === null
            ? {
                ...messagePayload,
                flow_spec: toFlowSpec(
                  store?.getState().nodes ?? [],
                  store?.getState().edges ?? [],
                  store?.getState().viewport ?? { x: 0, y: 0, zoom: 1 }
                ),
                session_id: sessionIdRef.current,
              }
            : messagePayload;

        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          let errDetail = t(
            "flowCanvas.playground.runFailedWithStatus",
            "Run failed with status {{status}}",
            { status: response.status }
          );
          try {
            const errJson = await response.json();
            if (errJson && errJson.detail)
              errDetail = formatErrorDetail(errJson.detail);
          } catch {
            // ignore
          }
          setError(errDetail);
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            const lastMsg = updated[lastIdx];
            if (
              lastIdx >= 0 &&
              lastMsg &&
              lastMsg.role === "assistant" &&
              !lastMsg.content
            ) {
              updated[lastIdx] = {
                role: "assistant",
                content: errDetail,
                isError: true,
              };
            }
            return updated;
          });
          return;
        }

        if (!response.body) {
          const errDetail = t(
            "flowCanvas.playground.noResponseStream",
            "No response stream received"
          );
          setError(errDetail);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let accumulatedAssistant = "";
        let accumulatedReasoning = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            const lines = part.split("\n");
            for (const line of lines) {
              const trimmedLine = line.trim();
              if (trimmedLine.startsWith("data:")) {
                const dataPayload = trimmedLine.slice(5).trim();
                if (dataPayload === "[DONE]") {
                  break;
                }

                try {
                  const event = JSON.parse(dataPayload);
                  if (
                    event.type === "graph_stage_start" &&
                    typeof event.stage_name === "string"
                  ) {
                    store?.getState().updateNodeRunStatus(event.stage_name, {
                      status: "running",
                      startedAt: Date.now(),
                      endedAt: null,
                      durationMs: null,
                    });
                  } else if (
                    event.type === "graph_stage_end" &&
                    typeof event.stage_name === "string"
                  ) {
                    const now = Date.now();
                    const prev =
                      store?.getState().nodeRunStatus[event.stage_name];
                    const started = prev?.startedAt ?? now;
                    store?.getState().updateNodeRunStatus(event.stage_name, {
                      status: "done",
                      endedAt: now,
                      durationMs: now - started,
                    });
                  } else if (event.type === "reasoning_start") {
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      isThinking: true,
                    }));
                  } else if (
                    event.type === "reasoning_delta" &&
                    typeof event.reasoning === "string"
                  ) {
                    accumulatedReasoning += event.reasoning;
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      reasoning: accumulatedReasoning,
                      isThinking: true,
                    }));
                  } else if (event.type === "reasoning_done") {
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      isThinking: false,
                    }));
                  } else if (
                    event.type === "token" &&
                    typeof event.content === "string"
                  ) {
                    accumulatedAssistant += event.content;
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      content: accumulatedAssistant,
                    }));
                  } else if (
                    event.type === "message" &&
                    typeof event.content === "string"
                  ) {
                    accumulatedAssistant = event.content;
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      content: accumulatedAssistant,
                    }));
                  } else if (event.type === "tool_call_start") {
                    const callId = String(
                      event.call_id ?? `tool-${Date.now()}`
                    );
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      toolCalls: [
                        ...(lastMsg.toolCalls ?? []),
                        {
                          callId,
                          name:
                            typeof event.name === "string"
                              ? event.name
                              : "tool",
                          input: event.input,
                          status: "running",
                        },
                      ],
                    }));
                  } else if (event.type === "tool_call_end") {
                    const callId = String(event.call_id ?? "");
                    patchAssistant((lastMsg) => {
                      const existing = lastMsg.toolCalls ?? [];
                      const idx = existing.findIndex(
                        (tc) => tc.callId === callId
                      );
                      const currentTc = idx >= 0 ? existing[idx] : undefined;
                      const patched: PlaygroundToolCall = {
                        callId: callId || `tool-${Date.now()}`,
                        name:
                          typeof event.name === "string" ? event.name : "tool",
                        input: currentTc?.input,
                        output: event.output,
                        status: "done",
                      };
                      const next =
                        idx >= 0 ? [...existing] : [...existing, patched];
                      if (idx >= 0 && currentTc)
                        next[idx] = { ...currentTc, ...patched };
                      return { ...lastMsg, toolCalls: next };
                    });
                  } else if (event.type === "usage") {
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      usage: {
                        inputTokens: Number(event.input_tokens) || 0,
                        outputTokens: Number(event.output_tokens) || 0,
                        totalTokens: Number(event.total_tokens) || 0,
                      },
                    }));
                  } else if (
                    event.type === "run_end" &&
                    typeof event.duration_ms === "number"
                  ) {
                    patchAssistant((lastMsg) => ({
                      ...lastMsg,
                      durationMs: event.duration_ms,
                    }));
                  } else if (event.type === "error") {
                    const errMsg =
                      typeof event.content === "string"
                        ? event.content
                        : JSON.stringify(event.content);
                    setError(errMsg);
                    setMessages((prev) => {
                      const updated = [...prev];
                      const lastIdx = updated.length - 1;
                      const lastMsg = updated[lastIdx];
                      if (
                        lastIdx >= 0 &&
                        lastMsg &&
                        lastMsg.role === "assistant"
                      ) {
                        updated[lastIdx] = {
                          role: "assistant",
                          content: errMsg,
                          isError: true,
                        };
                      }
                      return updated;
                    });
                  }
                } catch {
                  // ignore
                }
              }
            }
          }
        }
      } catch (err: unknown) {
        const msg =
          err instanceof Error
            ? err.message
            : t("flowCanvas.playground.networkError", "Network error");
        setError(msg);
        setMessages((prev) => {
          const updated = [...prev];
          const lastIdx = updated.length - 1;
          const lastMsg = updated[lastIdx];
          if (
            lastIdx >= 0 &&
            lastMsg &&
            lastMsg.role === "assistant" &&
            !lastMsg.content
          ) {
            updated[lastIdx] = {
              role: "assistant",
              content: msg,
              isError: true,
            };
          }
          return updated;
        });
      } finally {
        setIsRunning(false);
      }
    },
    [definitionId, patchAssistant, store, t]
  );

  const send = useCallback(
    async (text: string, files?: File[]) => {
      const trimmed = text.trim();
      const attachments = files ?? [];
      if ((!trimmed && attachments.length === 0) || isRunning) return;

      setIsRunning(true);
      setError(null);
      store?.getState().resetNodeRunStatus();

      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: trimmed,
          attachedFileNames:
            attachments.length > 0 ? attachments.map((f) => f.name) : undefined,
        },
        { role: "assistant", content: "" },
      ]);

      await runStream(text, attachments);
    },
    [isRunning, runStream, store]
  );

  const retry = useCallback(async () => {
    if (isRunning) return;

    const current = messagesRef.current;
    let lastUserIdx = -1;
    for (let i = current.length - 1; i >= 0; i--) {
      if (current[i]?.role === "user") {
        lastUserIdx = i;
        break;
      }
    }
    if (lastUserIdx === -1) return;
    const lastUserMsg = current[lastUserIdx];
    if (!lastUserMsg) return;
    const lastUserText = lastUserMsg.content;

    setIsRunning(true);
    setError(null);
    store?.getState().resetNodeRunStatus();
    // Drop everything after the last user message, then re-open a fresh
    // assistant turn. Attachments aren't replayable (base64 not retained)
    // so retry is text-only.
    setMessages((prev) => [
      ...prev.slice(0, lastUserIdx + 1),
      { role: "assistant", content: "" },
    ]);
    await runStream(lastUserText, []);
  }, [isRunning, runStream, store]);

  return { messages, isRunning, error, send, retry, clear };
}
