"use client";

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
} from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  uiMessageReducer,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { LangGraphLogoSVG } from "@/components/icons/langgraph";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { isUserSpecifiedDefaultAgent } from "@/lib/agent-utils";
import { useAuthContext } from "@/providers/Auth";
import { getDeployments } from "@/lib/environment/deployments";
import { useHasApiKeys } from "@/hooks/use-api-keys";
import { checkApiKeysWarning } from "@/lib/agent-utils";

export type StateType = { messages: Message[]; ui?: UIMessage[] };

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
    };
    CustomEventType: UIMessage | RemoveUIMessage;
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;
const StreamContext = createContext<StreamContextType | undefined>(undefined);

const StreamSession = ({
  children,
  agentId,
  deploymentId,
  accessToken,
  useProxyRoute,
}: {
  children: ReactNode;
  agentId: string;
  deploymentId: string;
  accessToken?: string;
  useProxyRoute?: boolean;
}) => {
  if (!useProxyRoute && !accessToken) {
    toast.error("Access token must be provided if not using proxy route");
  }

  const deployment = getDeployments().find((d) => d.id === deploymentId);
  if (!deployment) {
    throw new Error(`Deployment ${deploymentId} not found`);
  }

  let deploymentUrl = deployment.deploymentUrl;
  if (useProxyRoute) {
    const baseApiUrl = process.env.NEXT_PUBLIC_BASE_API_URL;
    if (!baseApiUrl) {
      throw new Error(
        "Failed to create client: Base API URL not configured. Please set NEXT_PUBLIC_BASE_API_URL",
      );
    }
    deploymentUrl = `${baseApiUrl}/langgraph/proxy/${deploymentId}`;
  }

  const [threadId, setThreadId] = useQueryState("threadId");

  // Ref to hold messages snapshot taken when the user cancels.
  // Used by the wrapped submit() to restore them as optimisticValues
  // so the next submit doesn't lose them.
  const cancelledMessagesRef = useRef<Message[] | null>(null);

  const streamValue = useTypedStream({
    apiUrl: deploymentUrl,
    assistantId: agentId,
    threadId: threadId ?? null,
    // reconnectOnMount enables runMetadataStorage (sessionStorage) which is
    // required for stop() → client.runs.cancel() to work.  Without it the
    // SDK never records the run_id so the cancel API call is skipped.
    reconnectOnMount: true,
    onCustomEvent: (event, options) => {
      options.mutate((prev) => {
        const ui = uiMessageReducer(prev.ui ?? [], event);
        return { ...prev, ui };
      });
    },
    onThreadId: (id) => {
      setThreadId(id);
    },
    defaultHeaders: {
      ...(!useProxyRoute
        ? {
          Authorization: `Bearer ${accessToken}`,
          "x-supabase-access-token": accessToken,
        }
        : {
          "x-auth-scheme": "langsmith",
        }),
    },
  });

  // ---- Wrapped stop ----
  // When the user clicks Cancel the SDK aborts the HTTP stream. Because
  // the abort fires before run.onSuccess(), the internal SWR cache that
  // backs `historyValues` is never refreshed.  The *next* submit() then
  // calls setStreamValues({ ...historyValues }) which is stale, so all
  // messages accumulated during the cancelled stream are lost.
  //
  // Fix: snapshot the current messages into a ref before calling stop().
  // The wrapped submit() below merges them back via optimisticValues so
  // the UI never loses them.
  const wrappedStop = useCallback(() => {
    // Snapshot messages BEFORE abort wipes the stream
    const msgs = streamValue.messages;
    if (msgs && msgs.length > 0) {
      cancelledMessagesRef.current = [...msgs];
    }
    streamValue.stop();
  }, [streamValue]);

  // ---- Wrapped submit ----
  // If a previous run was cancelled, inject the saved messages into
  // optimisticValues so they survive the historyValues reset.
  const wrappedSubmit: typeof streamValue.submit = useCallback(
    (values: any, submitOptions?: any) => {
      const savedMessages = cancelledMessagesRef.current;

      if (savedMessages && savedMessages.length > 0) {
        const originalOptimistic = submitOptions?.optimisticValues;

        const patchedOptimistic = (prev: StateType): StateType => {
          // Start from saved cancelled messages instead of stale history
          const base: StateType = { ...prev, messages: savedMessages };

          // Apply the caller's original optimistic transform on top
          if (typeof originalOptimistic === "function") {
            return originalOptimistic(base) as StateType;
          }
          if (originalOptimistic != null) {
            return { ...base, ...(originalOptimistic as Partial<StateType>) };
          }
          return base;
        };

        cancelledMessagesRef.current = null;

        return streamValue.submit(values, {
          ...submitOptions,
          optimisticValues: patchedOptimistic,
        });
      }

      // No cancelled messages — pass through unchanged
      return streamValue.submit(values, submitOptions);
    },
    [streamValue],
  );

  // Expose everything from streamValue but override stop and submit
  const contextValue = useMemo(
    () => ({
      ...streamValue,
      stop: wrappedStop,
      submit: wrappedSubmit,
    }),
    [streamValue, wrappedStop, wrappedSubmit],
  );

  return (
    <StreamContext.Provider value={contextValue}>
      {children}
    </StreamContext.Provider>
  );
};

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { agents, loading } = useAgentsContext();
  const [agentId, setAgentId] = useQueryState("agentId");
  const [deploymentId, setDeploymentId] = useQueryState("deploymentId");
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const { session } = useAuthContext();
  const hasApiKeys = useHasApiKeys();
  const warningShownRef = useRef<string>("");

  useEffect(() => {
    if (value || !agents.length) {
      return;
    }
    const defaultAgent = agents.find(isUserSpecifiedDefaultAgent);
    if (defaultAgent) {
      setValue(`${defaultAgent.assistant_id}:${defaultAgent.deploymentId}`);
    }
  }, [agents]);

  useEffect(() => {
    if (agentId && deploymentId) {
      const currentKey = `${agentId}:${deploymentId}`;
      if (warningShownRef.current !== currentKey) {
        checkApiKeysWarning(deploymentId, hasApiKeys);
        warningShownRef.current = currentKey;
      }
    }
  }, [agentId, deploymentId, hasApiKeys]);

  const handleValueChange = (v: string) => {
    setValue(v);
    setOpen(false);
  };

  const handleStartChat = () => {
    if (!value) {
      toast.info("Please select an agent");
      return;
    }
    const [agentId_, deploymentId_] = value.split(":");
    setAgentId(agentId_);
    setDeploymentId(deploymentId_);
  };

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!agentId || !deploymentId) {
    return (
      <div className="flex w-full items-center justify-center p-4">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-64 max-w-3xl flex-col rounded-lg border shadow-lg">
          <div className="mt-14 flex flex-col gap-2 p-6">
            <div className="flex flex-col items-start gap-2">
              <LangGraphLogoSVG className="h-7" />
              <h1 className="text-xl font-semibold tracking-tight">
                Open Agent Platform
              </h1>
            </div>
            <p className="text-muted-foreground">
              Welcome to Open Agent Platform's chat! To continue, please select
              an agent to chat with.
            </p>
          </div>
          <div className="mb-24 grid grid-cols-[1fr_auto] gap-4 px-6 pt-4">
            <AgentsCombobox
              disableDeselect
              agents={agents}
              agentsLoading={loading}
              value={value}
              setValue={(v) =>
                Array.isArray(v)
                  ? handleValueChange(v[0])
                  : handleValueChange(v)
              }
              open={open}
              setOpen={setOpen}
            />
            <Button onClick={handleStartChat}>Start Chat</Button>
          </div>
        </div>
      </div>
    );
  }

  const useProxyRoute = process.env.NEXT_PUBLIC_USE_LANGSMITH_AUTH === "true";
  if (!useProxyRoute && !session?.accessToken) {
    toast.error("Access token must be provided if not using proxy route");
    return null;
  }

  return (
    <StreamSession
      agentId={agentId}
      deploymentId={deploymentId}
      accessToken={session?.accessToken ?? undefined}
      useProxyRoute={useProxyRoute}
    >
      {children}
    </StreamSession>
  );
};

// Create a custom hook to use the context
export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
