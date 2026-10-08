import { PacketType } from "@/lib/api/domains/chat/message-types";
import {
  ActiveRunInfo,
  ChatRunActiveError,
  sendAfterOwnRunEnds,
} from "./resumableChatStream";

const packet = { obj: { type: "message_delta", content: "A" } } as never;
const activeRun = (clientRequestId: string | null): ActiveRunInfo => ({
  run_id: "r1",
  status: "running",
  started_at: 1,
  input_preview: "q",
  client_request_id: clientRequestId,
});

async function collect<T>(gen: AsyncGenerator<T>) {
  const out: T[] = [];
  for await (const item of gen) out.push(item);
  return out;
}

function sendSequence(outcomes: Array<"busy" | "ok">) {
  let call = 0;
  return jest.fn(async function* (): AsyncGenerator<PacketType> {
    const outcome = outcomes[call++];
    if (outcome === "busy") throw new ChatRunActiveError("r1");
    yield packet;
  });
}

const noSleep = jest.fn(async () => undefined);

it("retries while this tab's own stopped run still holds the thread", async () => {
  const send = sendSequence(["busy", "busy", "ok"]);
  const findActiveRun = jest.fn().mockResolvedValue(activeRun("mine"));

  const packets = await collect(
    sendAfterOwnRunEnds(send, {
      findActiveRun,
      isOwnRequest: (id) => id === "mine",
      signal: new AbortController().signal,
      sleep: noSleep,
    })
  );

  expect(packets).toEqual([packet]);
  expect(send).toHaveBeenCalledTimes(3);
});

it("retries at once when the thread was released in the meantime", async () => {
  const send = sendSequence(["busy", "ok"]);

  await collect(
    sendAfterOwnRunEnds(send, {
      findActiveRun: jest.fn().mockResolvedValue(null),
      isOwnRequest: () => false,
      signal: new AbortController().signal,
      sleep: noSleep,
    })
  );

  expect(send).toHaveBeenCalledTimes(2);
});

it("backs off instead of hammering the send when the active-run lookup fails", async () => {
  const send = sendSequence(["busy", "busy", "ok"]);
  const sleep = jest.fn(async (_ms: number) => undefined);

  await collect(
    sendAfterOwnRunEnds(send, {
      findActiveRun: jest.fn().mockRejectedValue(new Error("network")),
      isOwnRequest: () => false,
      signal: new AbortController().signal,
      sleep,
      backoffMs: (attempt) => attempt * 100,
    })
  );

  expect(send).toHaveBeenCalledTimes(3);
  expect(sleep.mock.calls.map(([ms]) => ms)).toEqual([100, 200]);
});

it("rethrows when another tab or device holds the thread", async () => {
  const send = sendSequence(["busy", "ok"]);

  await expect(
    collect(
      sendAfterOwnRunEnds(send, {
        findActiveRun: jest.fn().mockResolvedValue(activeRun("other")),
        isOwnRequest: (id) => id === "mine",
        signal: new AbortController().signal,
        sleep: noSleep,
      })
    )
  ).rejects.toBeInstanceOf(ChatRunActiveError);
  expect(send).toHaveBeenCalledTimes(1);
});

it("gives up after the attempt limit", async () => {
  const send = sendSequence(["busy", "busy", "busy"]);

  await expect(
    collect(
      sendAfterOwnRunEnds(send, {
        findActiveRun: jest.fn().mockResolvedValue(activeRun("mine")),
        isOwnRequest: () => true,
        signal: new AbortController().signal,
        sleep: noSleep,
        maxAttempts: 2,
      })
    )
  ).rejects.toBeInstanceOf(ChatRunActiveError);
  expect(send).toHaveBeenCalledTimes(2);
});

it("stops retrying once the user aborts", async () => {
  const controller = new AbortController();
  const send = sendSequence(["busy", "ok"]);

  const packets = await collect(
    sendAfterOwnRunEnds(send, {
      findActiveRun: jest.fn().mockResolvedValue(activeRun("mine")),
      isOwnRequest: () => true,
      signal: controller.signal,
      sleep: jest.fn(async () => controller.abort()),
    })
  );

  expect(packets).toEqual([]);
  expect(send).toHaveBeenCalledTimes(1);
});
