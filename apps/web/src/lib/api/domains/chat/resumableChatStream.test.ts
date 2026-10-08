import { handleSSEStream } from "@/lib/search/streamingUtils";
import {
  ActiveRunInfo,
  attachToRunStream,
  ChatRunExpiredError,
  ChatRunResyncRequiredError,
  resumableChatStream,
} from "./resumableChatStream";

const enc = new TextEncoder();
const frame = (id: number, data: string) => `id: ${id}\ndata: ${data}\n\n`;
const STARTED = '{"type":"run_started","run_id":"r1","thread_id":"t1"}';
const END = '{"type":"run_end","status":"completed","error_code":null}';
const tok = (c: string) => JSON.stringify({ type: "token", content: c });
const full = [
  frame(1, STARTED),
  frame(2, tok("A")),
  frame(3, tok("B")),
  frame(4, END),
  frame(5, "[DONE]"),
].join("");

function broken(text: string): Response {
  let sent = false;
  return new Response(
    new ReadableStream({
      pull(controller) {
        if (!sent) {
          sent = true;
          controller.enqueue(enc.encode(text));
        } else {
          controller.error(new TypeError("network error"));
        }
      },
    })
  );
}

async function collect<T>(gen: AsyncGenerator<T>) {
  const out: T[] = [];
  for await (const p of gen) out.push(p);
  return out;
}

const noSleep = jest.fn(async () => undefined);
const base = () => ({
  signal: new AbortController().signal,
  clientRequestId: "k1",
  sleep: noSleep,
  backoffMs: (n: number) => n * 10,
  findActiveRun: jest.fn(async () => null),
});

beforeEach(() => noSleep.mockClear());

it("re-attaches after a network drop and delivers every packet exactly once", async () => {
  const baseline = await collect(handleSSEStream(new Response(full)));
  const attach = jest.fn(async () => new Response(full));
  const packets = await collect(
    resumableChatStream({
      ...base(),
      open: async () => broken(frame(1, STARTED) + frame(2, tok("A"))),
      attach,
    })
  );
  expect(packets).toEqual(baseline);
  expect(attach).toHaveBeenCalledWith("r1", expect.anything());
  expect(noSleep).toHaveBeenCalledWith(10, expect.anything());
});

it("delivers every packet exactly once across two drops", async () => {
  const baseline = await collect(handleSSEStream(new Response(full)));
  const attach = jest
    .fn()
    .mockResolvedValueOnce(
      broken(frame(1, STARTED) + frame(2, tok("A")) + frame(3, tok("B")))
    )
    .mockResolvedValueOnce(new Response(full));
  const packets = await collect(
    resumableChatStream({
      ...base(),
      open: async () => broken(frame(1, STARTED)),
      attach,
    })
  );
  expect(packets).toEqual(baseline);
});

it("does not re-attach or throw after a user abort", async () => {
  const controller = new AbortController();
  const attach = jest.fn();
  const stream = resumableChatStream({
    ...base(),
    signal: controller.signal,
    open: async () =>
      new Response(
        new ReadableStream({
          start(c) {
            c.enqueue(enc.encode(frame(1, STARTED)));
          },
        })
      ),
    attach,
  });
  const first = stream.next();
  controller.abort();
  await first;
  await expect(collect(stream)).resolves.toBeDefined();
  expect(attach).not.toHaveBeenCalled();
});

it("throws ChatRunActiveError with the holder on 409", async () => {
  const open = async () =>
    new Response(
      JSON.stringify({
        statusCode: 409,
        error: {
          code: "chat_run.active",
          message: "busy",
          details: { run_id: "busy" },
        },
      }),
      { status: 409 }
    );
  await expect(
    collect(resumableChatStream({ ...base(), open, attach: jest.fn() }))
  ).rejects.toEqual(
    expect.objectContaining({ runId: "busy", name: "ChatRunActiveError" })
  );
});

it("attaches when the POST dies before run_started only if the run is this send's", async () => {
  const open = async () => {
    throw new TypeError("offline");
  };
  const mine: ActiveRunInfo = {
    run_id: "r1",
    status: "running",
    started_at: 1,
    input_preview: "",
    client_request_id: "k1",
  };
  const packets = await collect(
    resumableChatStream({
      ...base(),
      open,
      attach: async () => new Response(full),
      findActiveRun: async () => mine,
    })
  );
  expect(packets.length).toBeGreaterThan(0);
  await expect(
    collect(
      resumableChatStream({
        ...base(),
        open,
        attach: jest.fn(),
        findActiveRun: async () => ({ ...mine, client_request_id: "other" }),
      })
    )
  ).rejects.toThrow("offline");
});

it("gives up after the failure budget without progress", async () => {
  const attach = jest.fn(async () => {
    throw new TypeError("down");
  });
  await expect(
    collect(
      resumableChatStream({
        ...base(),
        maxConsecutiveFailures: 3,
        open: async () => broken(frame(1, STARTED)),
        attach,
      })
    )
  ).rejects.toThrow("down");
  expect(attach).toHaveBeenCalledTimes(3);
});

it("stops on resync and on an expired run", async () => {
  await expect(
    collect(
      resumableChatStream({
        ...base(),
        open: async () =>
          new Response('data: {"type":"resync","first_available_seq":9}\n\n'),
        attach: jest.fn(),
      })
    )
  ).rejects.toBeInstanceOf(ChatRunResyncRequiredError);
  await expect(
    collect(
      resumableChatStream({
        ...base(),
        open: async () => broken(frame(1, STARTED)),
        attach: async () => new Response("", { status: 404 }),
      })
    )
  ).rejects.toBeInstanceOf(ChatRunExpiredError);
});

it("ends cleanly when the stream closes after run_end", async () => {
  const attach = jest.fn();
  await collect(
    resumableChatStream({
      ...base(),
      open: async () => new Response(frame(1, STARTED) + frame(2, END)),
      attach,
    })
  );
  expect(attach).not.toHaveBeenCalled();
});

describe("replay boundary", () => {
  const CAUGHT_UP = 'data: {"type":"caught_up"}\n\n';
  const content = (p: { obj?: { type?: string; content?: string } }) =>
    p.obj?.type === "message_delta" ? p.obj.content ?? "" : null;

  /** Packets and replay changes in the exact order the consumer sees them. */
  async function trace(deps: Parameters<typeof resumableChatStream>[0]) {
    const log: string[] = [];
    const stream = resumableChatStream({
      ...deps,
      onReplayChange: (replaying) =>
        log.push(replaying ? "+replay" : "-replay"),
    });
    for await (const packet of stream) {
      const text = content(packet as never);
      if (text !== null) log.push(text);
    }
    return log;
  }

  it("never treats caught_up as a resync or yields it as a packet", async () => {
    const withMarker = [
      frame(1, STARTED),
      frame(2, tok("A")),
      CAUGHT_UP,
      frame(3, tok("B")),
      frame(4, END),
      frame(5, "[DONE]"),
    ].join("");
    const baseline = await collect(handleSSEStream(new Response(full)));
    const packets = await collect(
      resumableChatStream({
        ...base(),
        open: async () => new Response(withMarker),
        attach: jest.fn(),
      })
    );
    expect(packets).toEqual(baseline);
  });

  it("reports replay from the first packet of a page-load attach until caught_up", async () => {
    const body = [
      frame(1, STARTED),
      frame(2, tok("A")),
      frame(3, tok("B")),
      CAUGHT_UP,
      frame(4, tok("C")),
      frame(5, END),
      frame(6, "[DONE]"),
    ].join("");
    const log = await trace({
      ...base(),
      initialReplay: true,
      initialRunId: "r1",
      open: async () => new Response(body),
      attach: jest.fn(),
    });
    expect(log).toEqual(["+replay", "A", "B", "-replay", "C"]);
  });

  it("stays out of replay for a fresh send and ignores its own caught_up", async () => {
    const body = [
      frame(1, STARTED),
      CAUGHT_UP,
      frame(2, tok("A")),
      frame(3, END),
      frame(4, "[DONE]"),
    ].join("");
    const log = await trace({
      ...base(),
      open: async () => new Response(body),
      attach: jest.fn(),
    });
    expect(log).toEqual(["A"]);
  });

  it("ends the replay when the stream ends without caught_up (finished run, legacy backend)", async () => {
    const log = await trace({
      ...base(),
      initialReplay: true,
      initialRunId: "r1",
      open: async () => new Response(full),
      attach: jest.fn(),
    });
    expect(log).toEqual(["+replay", "A", "B", "-replay"]);
  });

  it("re-enters replay on a re-attach and leaves it at that stream's caught_up", async () => {
    const reattached = [
      frame(1, STARTED),
      frame(2, tok("A")),
      frame(3, tok("B")),
      CAUGHT_UP,
      frame(4, tok("C")),
      frame(5, END),
      frame(6, "[DONE]"),
    ].join("");
    const log = await trace({
      ...base(),
      open: async () => broken(frame(1, STARTED) + frame(2, tok("A"))),
      attach: jest.fn(async () => new Response(reattached)),
    });
    // A was already delivered live; B was missed and arrives as replay.
    expect(log).toEqual(["A", "+replay", "B", "-replay", "C"]);
  });

  it("reports each change once even when caught_up repeats", async () => {
    const body = [
      frame(1, STARTED),
      frame(2, tok("A")),
      CAUGHT_UP,
      CAUGHT_UP,
      frame(3, END),
      frame(4, "[DONE]"),
    ].join("");
    const onReplayChange = jest.fn();
    await collect(
      resumableChatStream({
        ...base(),
        initialReplay: true,
        initialRunId: "r1",
        onReplayChange,
        open: async () => new Response(body),
        attach: jest.fn(),
      })
    );
    expect(onReplayChange.mock.calls).toEqual([[true], [false]]);
  });

  it("leaves replay when the replay window has expired", async () => {
    const onReplayChange = jest.fn();
    await expect(
      collect(
        resumableChatStream({
          ...base(),
          initialReplay: true,
          initialRunId: "r1",
          onReplayChange,
          open: async () => new Response("", { status: 404 }),
          attach: jest.fn(async () => new Response("", { status: 404 })),
        })
      )
    ).rejects.toBeDefined();
    expect(onReplayChange).toHaveBeenLastCalledWith(false);
  });

  it("leaves replay when the user aborts mid-replay", async () => {
    const controller = new AbortController();
    const onReplayChange = jest.fn();
    const stream = resumableChatStream({
      ...base(),
      signal: controller.signal,
      initialReplay: true,
      initialRunId: "r1",
      onReplayChange,
      open: async () =>
        new Response(
          new ReadableStream({
            start(c) {
              c.enqueue(enc.encode(frame(1, STARTED) + frame(2, tok("A"))));
            },
          })
        ),
      attach: jest.fn(),
    });
    const first = stream.next();
    controller.abort();
    await first;
    await collect(stream);
    expect(onReplayChange.mock.calls).toEqual([[true], [false]]);
  });

  it("a page-load attach starts in replay and leaves it at caught_up", async () => {
    const body = [
      frame(1, STARTED),
      frame(2, tok("A")),
      CAUGHT_UP,
      frame(3, END),
      frame(4, "[DONE]"),
    ].join("");
    const log: string[] = [];
    const stream = attachToRunStream("r1", new AbortController().signal, {
      attach: async () => new Response(body),
      onReplayChange: (replaying) => log.push(replaying ? "+" : "-"),
    });
    for await (const packet of stream) {
      const text = content(packet as never);
      if (text !== null) log.push(text);
    }
    expect(log).toEqual(["+", "A", "-"]);
  });
});
