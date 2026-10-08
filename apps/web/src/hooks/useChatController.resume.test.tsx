import { act, renderHook, waitFor } from "@testing-library/react";
import { ReadonlyURLSearchParams } from "next/navigation";
import i18n from "@/i18n/config";
import {
  fetchActiveRun,
  fetchInitialChatSession,
  sendMessage,
  stopActiveChatSession,
} from "@/lib/api/domains/chat/api";
import {
  ActiveRunInfo,
  attachToRunStream,
  ChatRunActiveError,
  ChatRunExpiredError,
} from "@/lib/api/domains/chat/resumableChatStream";
import { PacketType } from "@/lib/api/domains/chat/message-types";
import { Message } from "@/lib/api/domains/chat/types";
import { toast } from "@/hooks/useToast";
import { useChatSessionStore } from "@/app/app/stores/useChatSessionStore";
import {
  getLatestMessageChain,
  MessageTreeState,
  SYSTEM_NODE_ID,
} from "@/app/app/services/messageTree";
import useChatController, { resolveAttachTarget } from "./useChatController";

jest.mock("next/navigation", () => ({
  ...jest.requireActual("next/navigation"),
  usePathname: () => "/app",
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
jest.mock("posthog-js/react", () => ({ usePostHog: () => null }));
jest.mock("@/lib/api/domains/chat/hooks", () => ({
  useChatSessions: () => ({
    refreshChatSessions: jest.fn(),
    addPendingChatSession: jest.fn(),
  }),
}));
jest.mock("@/lib/api/domains/preferences/hooks", () => ({
  useAgentPreferences: () => ({ agentPreferences: {} }),
}));
jest.mock("@/lib/hooks/useForcedTools", () => ({
  useForcedTools: () => ({ forcedToolIds: [] }),
}));
jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    fetchProjects: jest.fn(),
    setCurrentMessageFiles: jest.fn(),
    beginUpload: jest.fn(),
    uploadChatFiles: jest.fn(),
    currentProjectDetails: null,
  }),
}));
jest.mock("@/hooks/appNavigation", () => ({
  useAppParams: () => () => null,
}));
jest.mock("@/lib/api/domains/agents/hooks", () => ({
  usePublishedFlowSpec: () => ({ data: undefined }),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { error: jest.fn(), info: jest.fn(), success: jest.fn() },
}));
jest.mock("@/lib/api/domains/chat/api", () => ({
  createChatSession: jest.fn(),
  fetchActiveRun: jest.fn(),
  fetchAgentDocumentTokenMaximum: jest.fn(),
  fetchInitialChatSession: jest.fn(),
  markChatSessionSeen: jest.fn().mockResolvedValue(undefined),
  renameChatSession: jest.fn(),
  seedChatFromSlack: jest.fn(),
  sendMessage: jest.fn(),
  stopActiveChatSession: jest.fn(),
  updateLlmOverrideForChatSession: jest.fn(),
}));
jest.mock("@/lib/api/domains/chat/resumableChatStream", () => ({
  ...jest.requireActual("@/lib/api/domains/chat/resumableChatStream"),
  attachToRunStream: jest.fn(),
}));

const SESSION = "s1";
const placement = { turn_index: 0, sub_turn_index: null };

const run: ActiveRunInfo = {
  run_id: "r9",
  status: "running",
  started_at: 1,
  input_preview: "q",
  client_request_id: null,
};

function answerPackets(text: string): PacketType[] {
  return [
    {
      placement,
      obj: { type: "message_start", content: "", final_documents: null },
    },
    { placement, obj: { type: "message_delta", content: text } },
    { placement, obj: { type: "stop", stop_reason: "finished" } },
  ] as unknown as PacketType[];
}

async function* packetStream(
  items: PacketType[],
  error?: Error
): AsyncGenerator<PacketType, void, unknown> {
  for (const item of items) yield item;
  if (error) throw error;
}

function node(
  nodeId: number,
  parentNodeId: number | null,
  type: Message["type"],
  message: string,
  messageId?: number
): Message {
  return {
    nodeId,
    parentNodeId,
    type,
    message,
    messageId,
    files: [],
    toolCall: null,
    packets: [],
  };
}

function seedHistory(messages: Message[]): MessageTreeState {
  const tree: MessageTreeState = new Map();
  const all = [node(SYSTEM_NODE_ID, null, "system", ""), ...messages];
  for (const message of all) {
    const children = all
      .filter((m) => m.parentNodeId === message.nodeId)
      .map((m) => m.nodeId);
    tree.set(message.nodeId, {
      ...message,
      childrenNodeIds: children,
      latestChildNodeId: children[children.length - 1] ?? null,
    });
  }
  const store = useChatSessionStore.getState();
  store.createSession(SESSION);
  store.setCurrentSession(SESSION);
  store.updateSessionMessageTree(SESSION, tree);
  return tree;
}

function sessionTree(): MessageTreeState {
  return useChatSessionStore.getState().sessions.get(SESSION)!.messageTree;
}

const restoreInputBar = jest.fn();

function renderController() {
  return renderHook(() =>
    useChatController({
      filterManager: {
        selectedSources: [],
        selectedDocumentSets: [],
        selectedTags: [],
        timeRange: null,
      } as never,
      llmManager: {
        currentLlm: { name: "", provider: "", modelName: "" },
        temperature: 0,
        llmProviders: [],
        updateImageFilesPresent: jest.fn(),
      } as never,
      liveAgent: undefined,
      availableAgents: [],
      existingChatSessionId: SESSION,
      selectedDocuments: [],
      searchParams: new URLSearchParams() as unknown as ReadonlyURLSearchParams,
      resetInputBar: jest.fn(),
      setSelectedAgentFromId: jest.fn(),
      restoreInputBar,
    })
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  useChatSessionStore.setState({
    sessions: new Map(),
    currentSessionId: null,
  });
});

describe("resolveAttachTarget", () => {
  const user = node(1, SYSTEM_NODE_ID, "user", "q", 10);

  it("reuses the last user message when it is the run's input", () => {
    expect(resolveAttachTarget([user], "q")).toEqual({ userNode: user });
  });

  it("reuses the last user message behind a partial answer", () => {
    const partial = node(2, 1, "assistant", "half");
    expect(resolveAttachTarget([user, partial], "q")).toEqual({
      userNode: user,
    });
  });

  it("matches a long message against its truncated preview", () => {
    const long = node(1, SYSTEM_NODE_ID, "user", "x".repeat(2500), 10);
    expect(resolveAttachTarget([long], "x".repeat(2000))).toEqual({
      userNode: long,
    });
  });

  it("creates the user message under the chain's end when it is missing", () => {
    const answer = node(2, 1, "assistant", "a", 11);
    expect(resolveAttachTarget([user, answer], "another question")).toEqual({
      parentNodeId: 2,
    });
  });

  it("starts from the system node in an empty chat", () => {
    expect(resolveAttachTarget([], "q")).toEqual({
      parentNodeId: SYSTEM_NODE_ID,
    });
  });
});

describe("useChatController resumable runs", () => {
  it("409 on send attaches instead of rendering an error", async () => {
    seedHistory([
      node(1, SYSTEM_NODE_ID, "user", "q0", 10),
      node(2, 1, "assistant", "a0", 11),
    ]);
    jest
      .mocked(sendMessage)
      .mockReturnValue(packetStream([], new ChatRunActiveError("r9")));
    jest.mocked(fetchActiveRun).mockResolvedValue(run);
    jest
      .mocked(attachToRunStream)
      .mockImplementation(() => packetStream(answerPackets("Hello")));

    const { result } = renderController();
    await act(async () => {
      await result.current.onSubmit({
        message: "my new question",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });

    expect(toast.error).toHaveBeenCalledWith(
      i18n.t("chat.toasts.runStillActive")
    );
    // The turned-away message goes back into the input bar.
    expect(restoreInputBar).toHaveBeenCalledWith("my new question", []);
    await waitFor(() =>
      expect(jest.mocked(attachToRunStream).mock.calls[0]?.[0]).toBe("r9")
    );
    await waitFor(() =>
      expect(getLatestMessageChain(sessionTree()).at(-1)?.message).toBe("Hello")
    );
    const tree = sessionTree();
    const chain = getLatestMessageChain(tree);
    expect(Array.from(tree.values()).some((m) => m.type === "error")).toBe(
      false
    );
    // The rejected send left nothing behind; the running answer sits under
    // the run's own message.
    expect(chain.map((m) => m.message)).toEqual(["q0", "a0", "q", "Hello"]);
    expect(
      useChatSessionStore.getState().sessions.get(SESSION)?.chatState
    ).toBe("input");
  });

  it("attachToActiveRun renders the running answer under the last user message", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    jest
      .mocked(attachToRunStream)
      .mockImplementation(() => packetStream(answerPackets("Hello")));

    const { result } = renderController();
    await act(async () => {
      await Promise.all([
        result.current.attachToActiveRun(SESSION, run),
        result.current.attachToActiveRun(SESSION, run),
      ]);
    });

    expect(attachToRunStream).toHaveBeenCalledTimes(1);
    const tree = sessionTree();
    const chain = getLatestMessageChain(tree);
    const users = Array.from(tree.values()).filter((m) => m.type === "user");
    expect(users).toHaveLength(1);
    expect(chain.map((m) => m.type)).toEqual(["user", "assistant"]);
    expect(chain[1]?.parentNodeId).toBe(1);
    expect(chain[1]?.message).toBe("Hello");
    // The reused user node keeps its persisted id.
    expect(chain[0]?.messageId).toBe(10);
  });

  it("attachToActiveRun is a no-op while the session already streams", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    useChatSessionStore.getState().updateChatState(SESSION, "streaming");

    const { result } = renderController();
    await act(async () => {
      await result.current.attachToActiveRun(SESSION, run);
    });

    expect(attachToRunStream).not.toHaveBeenCalled();
  });

  it("an expired replay shows the saved conversation", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    jest
      .mocked(attachToRunStream)
      .mockImplementation(() =>
        packetStream([], new ChatRunExpiredError("r9"))
      );
    jest.mocked(fetchInitialChatSession).mockResolvedValue(
      new Response(
        JSON.stringify({
          messages: [
            {
              message_id: 10,
              message_type: "user",
              message: "q",
              parent_message: null,
              latest_child_message: 11,
              files: [],
              time_sent: "2026-09-26T10:00:00Z",
            },
            {
              message_id: 11,
              message_type: "assistant",
              message: "persisted answer",
              parent_message: 10,
              latest_child_message: null,
              files: [],
              time_sent: "2026-09-26T10:00:05Z",
            },
          ],
          packets: [[], []],
        })
      )
    );

    const { result } = renderController();
    await act(async () => {
      await result.current.attachToActiveRun(SESSION, run);
    });

    expect(toast.info).toHaveBeenCalledWith(
      i18n.t("chat.toasts.runReplayExpired")
    );
    expect(fetchInitialChatSession).toHaveBeenCalledWith(
      SESSION,
      expect.anything()
    );
    const chain = getLatestMessageChain(sessionTree());
    expect(chain.at(-1)?.message).toBe("persisted answer");
    expect(
      Array.from(sessionTree().values()).some((m) => m.type === "error")
    ).toBe(false);
  });

  it("unmounting mid-stream never calls the stop endpoint", async () => {
    seedHistory([]);
    jest.mocked(sendMessage).mockImplementation(async function* (params) {
      await new Promise<void>(
        (resolve) => params.signal?.addEventListener("abort", () => resolve())
      );
    });

    const { result, unmount } = renderController();
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.onSubmit({
        message: "long question",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const streamController = useChatSessionStore
      .getState()
      .sessions.get(SESSION)?.abortController;

    unmount();
    expect(stopActiveChatSession).not.toHaveBeenCalled();

    // Let the pending send finish so no timer outlives the test.
    await act(async () => {
      streamController?.abort();
      await pending;
    });
    expect(stopActiveChatSession).not.toHaveBeenCalled();
  });

  it("a send right after Stop waits for the stopped run instead of attaching to it", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    let firstRequestId: string | undefined;
    jest.mocked(sendMessage).mockImplementation(async function* (params) {
      if (firstRequestId === undefined) {
        // The first send streams until the user stops it.
        firstRequestId = params.idempotencyKey;
        await new Promise<void>(
          (resolve) => params.signal?.addEventListener("abort", () => resolve())
        );
        return;
      }
      if (jest.mocked(sendMessage).mock.calls.length === 2) {
        // The stopped run still holds the thread for a moment.
        throw new ChatRunActiveError("r1");
      }
      yield* packetStream(answerPackets("Second answer"));
    });
    jest
      .mocked(stopActiveChatSession)
      .mockResolvedValue(new Response(null, { status: 200 }));
    jest.mocked(fetchActiveRun).mockImplementation(async () => ({
      ...run,
      run_id: "r1",
      client_request_id: firstRequestId ?? null,
    }));

    const { result } = renderController();
    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.onSubmit({
        message: "first",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    await act(async () => {
      await result.current.stopGenerating();
      await first;
    });

    // The stopped run must not be replayed by a visibility/online lookup.
    await act(async () => {
      await result.current.attachToActiveRun(SESSION, {
        ...run,
        run_id: "r1",
        client_request_id: firstRequestId ?? null,
      });
    });
    expect(attachToRunStream).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.onSubmit({
        message: "second",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });

    expect(toast.error).not.toHaveBeenCalled();
    expect(attachToRunStream).not.toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledTimes(3);
    const chain = getLatestMessageChain(sessionTree());
    expect(chain.at(-1)?.message).toBe("Second answer");
    expect(chain.at(-2)?.message).toBe("second");
  }, 15000);

  it("Stop while the send is still loading names that send, and no later token renders", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    let requestId: string | undefined;
    jest.mocked(sendMessage).mockImplementation(async function* (params) {
      requestId = params.idempotencyKey;
      yield* packetStream(answerPackets("A").slice(0, 2));
      await new Promise<void>(
        (resolve) => params.signal?.addEventListener("abort", () => resolve())
      );
      // A packet already in flight when the user pressed Stop.
      yield* packetStream(answerPackets("B").slice(1, 2));
    });
    jest
      .mocked(stopActiveChatSession)
      .mockResolvedValue(new Response(null, { status: 200 }));

    const { result } = renderController();
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.onSubmit({
        message: "long question",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });
    await waitFor(() =>
      expect(getLatestMessageChain(sessionTree()).at(-1)?.message).toBe("A")
    );

    await act(async () => {
      await result.current.stopGenerating();
      await pending;
    });

    expect(stopActiveChatSession).toHaveBeenCalledWith(SESSION, requestId);
    expect(requestId).toBeTruthy();
    expect(getLatestMessageChain(sessionTree()).at(-1)?.message).toBe("A");
    expect(
      useChatSessionStore.getState().sessions.get(SESSION)?.chatState
    ).toBe("input");
  });
});

describe("useChatController replayed history", () => {
  type ReplayHook = { onReplayChange?: (replaying: boolean) => void };

  // Fresh objects per use, like the parser makes: the controller tags packets
  // in place, so a shared fixture would leak the flag across tests.
  const start = () => ({
    placement,
    obj: { type: "message_start", content: "", final_documents: null },
  });
  const delta = (content: string) => ({
    placement,
    obj: { type: "message_delta", content },
  });
  const stop = () => ({
    placement,
    obj: { type: "stop", stop_reason: "finished" },
  });

  function publishedPackets() {
    const chain = getLatestMessageChain(sessionTree());
    return chain.at(-1)!.packets as unknown as { replayed?: boolean }[];
  }

  /** A stream that reports replay changes between its packets, as the real one does. */
  function replayingStream(
    deps: ReplayHook | undefined,
    script: (PacketType | boolean)[]
  ): AsyncGenerator<PacketType, void, unknown> {
    return (async function* () {
      for (const step of script) {
        if (typeof step === "boolean") deps?.onReplayChange?.(step);
        else yield step;
      }
    })();
  }

  it("tags packets that arrive during a page-load replay, and only those", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    jest
      .mocked(attachToRunStream)
      .mockImplementation((_id, _signal, deps) =>
        replayingStream(
          deps as ReplayHook,
          [
            true,
            start(),
            delta("Alpha ") as never,
            delta("Beta ") as never,
            false,
            delta("Gamma") as never,
            stop() as never,
          ] as never
        )
      );

    const { result } = renderController();
    await act(async () => {
      await result.current.attachToActiveRun(SESSION, run);
    });

    expect(publishedPackets().map((p) => p.replayed === true)).toEqual([
      true,
      true,
      true,
      false,
      false,
    ]);
    expect(getLatestMessageChain(sessionTree()).at(-1)?.message).toBe(
      "Alpha Beta Gamma"
    );
  });

  it("tags nothing when the stream never reports a replay", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
    jest
      .mocked(attachToRunStream)
      .mockImplementation(() => packetStream(answerPackets("Hello")));

    const { result } = renderController();
    await act(async () => {
      await result.current.attachToActiveRun(SESSION, run);
    });

    expect(publishedPackets().some((p) => p.replayed)).toBe(false);
  });

  it("tags the packets a re-attach replays after a dropped connection", async () => {
    seedHistory([node(1, SYSTEM_NODE_ID, "user", "q0", 10)]);
    jest.mocked(sendMessage).mockImplementation(((params: ReplayHook) =>
      replayingStream(params, [
        start(),
        delta("Live ") as never,
        true, // connection dropped; the re-attach replays what was missed
        delta("Missed ") as never,
        false,
        delta("Fresh") as never,
        stop() as never,
      ] as never)) as never);

    const { result } = renderController();
    await act(async () => {
      await result.current.onSubmit({
        message: "next",
        currentMessageFiles: [],
        deepResearch: false,
      });
    });

    expect(publishedPackets().map((p) => p.replayed === true)).toEqual([
      false,
      false,
      true,
      false,
      false,
    ]);
  });

  it("publishes a long replay in a few updates, not one per packet", async () => {
    const total = 60;
    const words = Array.from({ length: total }, (_, i) => `w${i} `);
    const replayScript = () => [
      true,
      start(),
      ...words.map(delta),
      false,
      stop(),
    ];
    const liveScript = () => [start(), ...words.map(delta), stop()];

    async function publishesFor(replaying: boolean) {
      jest.clearAllMocks();
      useChatSessionStore.setState({
        sessions: new Map(),
        currentSessionId: null,
      });
      seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
      jest
        .mocked(attachToRunStream)
        .mockImplementation((_id, _signal, deps) =>
          replayingStream(
            deps as ReplayHook,
            (replaying ? replayScript() : liveScript()) as never
          )
        );
      let publishes = 0;
      let last = sessionTree();
      const unsubscribe = useChatSessionStore.subscribe((state) => {
        const tree = state.sessions.get(SESSION)?.messageTree;
        if (tree && tree !== last) {
          last = tree;
          publishes += 1;
        }
      });
      const { result } = renderController();
      await act(async () => {
        await result.current.attachToActiveRun(SESSION, run);
      });
      unsubscribe();
      return publishes;
    }

    const live = await publishesFor(false);
    const replayed = await publishesFor(true);

    expect(getLatestMessageChain(sessionTree()).at(-1)?.message).toBe(
      words.join("")
    );
    expect(live).toBeGreaterThan(total / 2);
    expect(replayed).toBeLessThan(10);
  });

  describe("attach placeholder", () => {
    const assistantNode = () => getLatestMessageChain(sessionTree()).at(-1);

    function gate() {
      let release!: () => void;
      const opened = new Promise<void>((resolve) => (release = resolve));
      return { opened, release };
    }

    it("marks the answer as resuming until the replay's content is published", async () => {
      seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
      const held = gate();
      jest.mocked(attachToRunStream).mockImplementation((_id, _signal, deps) =>
        (async function* () {
          (deps as ReplayHook).onReplayChange?.(true);
          await held.opened;
          yield start() as never;
          yield delta("Hello") as never;
          (deps as ReplayHook).onReplayChange?.(false);
          yield stop() as never;
        })()
      );

      const { result } = renderController();
      let attaching!: Promise<void>;
      act(() => {
        attaching = result.current.attachToActiveRun(SESSION, run);
      });

      await waitFor(() => expect(assistantNode()?.type).toBe("assistant"));
      expect(assistantNode()?.resuming).toBe(true);
      expect(assistantNode()?.packets).toHaveLength(0);

      held.release();
      await act(async () => {
        await attaching;
      });
      expect(assistantNode()?.message).toBe("Hello");
      expect(assistantNode()?.resuming).toBeFalsy();
    });

    it("drops the placeholder once the replay found nothing to show", async () => {
      seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
      const held = gate();
      jest.mocked(attachToRunStream).mockImplementation((_id, _signal, deps) =>
        (async function* () {
          (deps as ReplayHook).onReplayChange?.(true);
          (deps as ReplayHook).onReplayChange?.(false); // caught up, empty log
          await held.opened; // the run is quiet: nothing live yet either
          yield start() as never;
          yield delta("Later") as never;
          yield stop() as never;
        })()
      );

      const { result } = renderController();
      let attaching!: Promise<void>;
      act(() => {
        attaching = result.current.attachToActiveRun(SESSION, run);
      });

      // No packet ever arrived, yet the skeleton must not linger.
      await waitFor(() => {
        expect(assistantNode()?.type).toBe("assistant");
        expect(assistantNode()?.resuming).toBe(false);
      });

      held.release();
      await act(async () => {
        await attaching;
      });
      expect(assistantNode()?.message).toBe("Later");
    });

    it("never leaves the placeholder behind when the stream ends empty", async () => {
      seedHistory([node(1, SYSTEM_NODE_ID, "user", "q", 10)]);
      jest.mocked(attachToRunStream).mockImplementation(() => packetStream([]));

      const { result } = renderController();
      await act(async () => {
        await result.current.attachToActiveRun(SESSION, run);
      });

      expect(assistantNode()?.resuming).toBeFalsy();
    });

    it("a fresh send is never marked as resuming", async () => {
      seedHistory([node(1, SYSTEM_NODE_ID, "user", "q0", 10)]);
      jest
        .mocked(sendMessage)
        .mockImplementation(() => packetStream(answerPackets("Hi")));

      const { result } = renderController();
      await act(async () => {
        await result.current.onSubmit({
          message: "next",
          currentMessageFiles: [],
          deepResearch: false,
        });
      });

      const nodes = Array.from(sessionTree().values());
      expect(nodes.some((m) => m.resuming)).toBe(false);
    });
  });
});
