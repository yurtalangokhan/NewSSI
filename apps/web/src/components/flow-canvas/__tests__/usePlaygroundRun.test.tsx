import { act, renderHook } from "@testing-library/react";
import { usePlaygroundRun } from "../hooks/usePlaygroundRun";
import { createFlowStore } from "../stores/flowStore";

function createMockStream(chunks: string[]) {
  const encoded = chunks.map((c) => new TextEncoder().encode(c));
  let idx = 0;
  return {
    getReader() {
      return {
        async read() {
          if (idx < encoded.length) {
            return { value: encoded[idx++], done: false };
          }
          return { value: undefined, done: true };
        },
      };
    },
  };
}

describe("usePlaygroundRun", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("44.3 — send appends user message immediately and triggers stream fetch", async () => {
    const stream = createMockStream([
      'data: {"type": "token", "content": "Hi "}\n\n',
      'data: {"type": "token", "content": "there!"}\n\n',
      "data: [DONE]\n\n",
    ]);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: stream,
    } as any);

    const { result } = renderHook(() => usePlaygroundRun("def-1"));

    await act(async () => {
      await result.current.send("Hello");
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/agent-definitions/def-1/flow/playground/runs/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ message: "Hello" }),
      })
    );

    expect(result.current.messages).toEqual([
      { role: "user", content: "Hello" },
      { role: "assistant", content: "Hi there!" },
    ]);
    expect(result.current.isRunning).toBe(false);
  });

  it("surfaces a structured validation error (FastAPI {errors:[...]} detail) as readable text, not [object Object]", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: {
          errors: [
            {
              code: "FLOW_NO_EXIT",
              message: "The flow has no path to a Chat Output node.",
            },
          ],
        },
      }),
    } as any);

    const { result } = renderHook(() => usePlaygroundRun("def-1"));

    await act(async () => {
      await result.current.send("test");
    });

    expect(result.current.error).toBe(
      "The flow has no path to a Chat Output node."
    );
    expect(result.current.error).not.toContain("[object Object]");
  });

  it("44.6 — surfaces error events cleanly without throwing", async () => {
    const stream = createMockStream([
      'data: {"type": "error", "content": "Tool execution failed"}\n\n',
    ]);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: stream,
    } as any);

    const { result } = renderHook(() => usePlaygroundRun("def-1"));

    await act(async () => {
      await result.current.send("Trigger error");
    });

    expect(result.current.error).toBe("Tool execution failed");
    expect(result.current.messages[1]).toEqual({
      role: "assistant",
      content: "Tool execution failed",
      isError: true,
    });
  });

  it("44.8 — switching definitionId resets messages and error state", async () => {
    const stream = createMockStream([
      'data: {"type": "message", "content": "Resp 1"}\n\n',
    ]);

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      body: stream,
    } as any);

    const { result, rerender } = renderHook(
      ({ defId }) => usePlaygroundRun(defId),
      {
        initialProps: { defId: "def-1" },
      }
    );

    await act(async () => {
      await result.current.send("Msg 1");
    });

    expect(result.current.messages.length).toBe(2);

    rerender({ defId: "def-2" });

    expect(result.current.messages).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  describe("reasoning stream (Thinking… block)", () => {
    it("accumulates reasoning_delta events into a separate reasoning field, distinct from the answer content", async () => {
      const stream = createMockStream([
        'data: {"type": "reasoning_start"}\n\n',
        'data: {"type": "reasoning_delta", "reasoning": "Let"}\n\n',
        'data: {"type": "reasoning_delta", "reasoning": " me think..."}\n\n',
        'data: {"type": "reasoning_done"}\n\n',
        'data: {"type": "token", "content": "Hello!"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));

      await act(async () => {
        await result.current.send("hi");
      });

      expect(result.current.messages[1]).toEqual({
        role: "assistant",
        content: "Hello!",
        reasoning: "Let me think...",
        isThinking: false,
      });
    });

    it("marks the message as isThinking while reasoning is in progress, before any answer content arrives", async () => {
      const resolveSecondReadRef: { current: (() => void) | null } = {
        current: null,
      };
      const firstChunk = new TextEncoder().encode(
        'data: {"type": "reasoning_start"}\n\ndata: {"type": "reasoning_delta", "reasoning": "hmm"}\n\n'
      );
      let readCount = 0;
      const stream = {
        getReader() {
          return {
            async read() {
              readCount += 1;
              if (readCount === 1) return { value: firstChunk, done: false };
              await new Promise<void>((resolve) => {
                resolveSecondReadRef.current = resolve;
              });
              return { value: undefined, done: true };
            },
          };
        },
      };
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));

      let sendPromise!: Promise<void>;
      act(() => {
        sendPromise = result.current.send("hi");
      });
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(result.current.messages[1]?.isThinking).toBe(true);
      expect(result.current.messages[1]?.reasoning).toBe("hmm");
      expect(result.current.messages[1]?.content).toBe("");

      resolveSecondReadRef.current?.();
      await act(async () => {
        await sendPromise;
      });
    });
  });

  describe("file attachments", () => {
    it("sends attached files as inline base64 content blocks on the message, not the plain `message` field", async () => {
      const stream = createMockStream([
        'data: {"type": "message", "content": "got it"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      const file = new File(["hello world"], "notes.txt", {
        type: "text/plain",
      });

      await act(async () => {
        await result.current.send("Summarize this", [file]);
      });

      const call = (global.fetch as jest.Mock).mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.message).toBeUndefined();
      expect(body.input.messages).toEqual([
        {
          role: "user",
          content: [
            { type: "text", text: "Summarize this" },
            {
              type: "file",
              mime_type: "text/plain",
              data: expect.any(String),
              metadata: { filename: "notes.txt" },
            },
          ],
        },
      ]);

      expect(result.current.messages[0]).toEqual({
        role: "user",
        content: "Summarize this",
        attachedFileNames: ["notes.txt"],
      });
    });

    it("allows sending a file with no text — the trimmed text is still an empty string, not blocked", async () => {
      const stream = createMockStream([
        'data: {"type": "message", "content": "ok"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      const file = new File(["data"], "report.pdf", {
        type: "application/pdf",
      });

      await act(async () => {
        await result.current.send("   ", [file]);
      });

      expect(global.fetch).toHaveBeenCalledTimes(1);
      const body = JSON.parse(
        (global.fetch as jest.Mock).mock.calls[0][1].body
      );
      expect(body.input.messages[0].content[0]).toEqual({
        type: "text",
        text: "",
      });
    });
  });

  describe("inline mode (no definitionId — flow not saved yet)", () => {
    it("posts the store's current graph to the inline endpoint instead of fetching by id", async () => {
      const stream = createMockStream([
        'data: {"type": "message", "content": "Hi from draft"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const store = createFlowStore();
      store.getState().setNodes([
        {
          id: "in",
          position: { x: 0, y: 0 },
          data: { type: "ChatInput", templateVersion: 1, values: {} },
        } as any,
      ]);

      const { result } = renderHook(() => usePlaygroundRun(null, store));

      await act(async () => {
        await result.current.send("Hello draft");
      });

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/agent-definitions/flow/playground/runs/stream",
        expect.objectContaining({ method: "POST" })
      );
      const call = (global.fetch as jest.Mock).mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.message).toBe("Hello draft");
      expect(body.flow_spec.nodes).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ id: "in", type: "ChatInput" }),
        ])
      );
      expect(typeof body.session_id).toBe("string");
      expect(body.session_id.length).toBeGreaterThan(0);

      expect(result.current.messages[1]).toEqual({
        role: "assistant",
        content: "Hi from draft",
      });
    });

    it("reuses the same session_id across multiple sends", async () => {
      const stream1 = createMockStream([
        'data: {"type": "message", "content": "1"}\n\n',
      ]);
      const stream2 = createMockStream([
        'data: {"type": "message", "content": "2"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({ ok: true, body: stream1 } as any)
        .mockResolvedValueOnce({ ok: true, body: stream2 } as any);

      const store = createFlowStore();
      const { result } = renderHook(() => usePlaygroundRun(null, store));

      await act(async () => {
        await result.current.send("first");
      });
      await act(async () => {
        await result.current.send("second");
      });

      const calls = (global.fetch as jest.Mock).mock.calls;
      const sessionId1 = JSON.parse(calls[0][1].body).session_id;
      const sessionId2 = JSON.parse(calls[1][1].body).session_id;
      expect(sessionId1).toBe(sessionId2);
    });
  });

  describe("rich playground events (tool calls, usage, duration)", () => {
    it("accumulates tool_call_start / tool_call_end into toolCalls on the assistant message", async () => {
      const stream = createMockStream([
        'data: {"type": "tool_call_start", "call_id": "t1", "name": "perform_search", "input": {"query": "Türksat"}}\n\n',
        'data: {"type": "tool_call_end", "call_id": "t1", "name": "perform_search", "output": [{"title": "Türksat - Vikipedi"}]}\n\n',
        'data: {"type": "token", "content": "Done."}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      await act(async () => {
        await result.current.send("ara");
      });

      expect(result.current.messages[1]!.toolCalls).toEqual([
        {
          callId: "t1",
          name: "perform_search",
          input: { query: "Türksat" },
          output: [{ title: "Türksat - Vikipedi" }],
          status: "done",
        },
      ]);
      expect(result.current.messages[1]!.content).toBe("Done.");
    });

    it("stores the latest cumulative usage event on the assistant message", async () => {
      const stream = createMockStream([
        'data: {"type": "usage", "input_tokens": 100, "output_tokens": 10, "total_tokens": 110}\n\n',
        'data: {"type": "usage", "input_tokens": 33800, "output_tokens": 370, "total_tokens": 34170}\n\n',
        'data: {"type": "token", "content": "hi"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      await act(async () => {
        await result.current.send("q");
      });

      expect(result.current.messages[1]!.usage).toEqual({
        inputTokens: 33800,
        outputTokens: 370,
        totalTokens: 34170,
      });
    });

    it("stores run_end duration_ms as durationMs on the assistant message", async () => {
      const stream = createMockStream([
        'data: {"type": "token", "content": "hi"}\n\n',
        'data: {"type": "run_end", "duration_ms": 66300}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValue({ ok: true, body: stream } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      await act(async () => {
        await result.current.send("q");
      });

      expect(result.current.messages[1]!.durationMs).toBe(66300);
    });
  });

  describe("retry", () => {
    it("re-runs the last user turn, replacing the previous assistant reply", async () => {
      const first = createMockStream([
        'data: {"type": "token", "content": "first answer"}\n\n',
      ]);
      const second = createMockStream([
        'data: {"type": "token", "content": "second answer"}\n\n',
      ]);
      global.fetch = jest
        .fn()
        .mockResolvedValueOnce({ ok: true, body: first } as any)
        .mockResolvedValueOnce({ ok: true, body: second } as any);

      const { result } = renderHook(() => usePlaygroundRun("def-1"));
      await act(async () => {
        await result.current.send("hello");
      });
      expect(result.current.messages).toEqual([
        { role: "user", content: "hello" },
        { role: "assistant", content: "first answer" },
      ]);

      await act(async () => {
        await result.current.retry();
      });

      expect(global.fetch).toHaveBeenCalledTimes(2);
      expect(result.current.messages).toEqual([
        { role: "user", content: "hello" },
        { role: "assistant", content: "second answer" },
      ]);
    });

    it("is a no-op when there is no user message yet", async () => {
      global.fetch = jest.fn();
      const { result } = renderHook(() => usePlaygroundRun("def-1"));

      await act(async () => {
        await result.current.retry();
      });

      expect(global.fetch).not.toHaveBeenCalled();
      expect(result.current.messages).toEqual([]);
    });
  });
});
