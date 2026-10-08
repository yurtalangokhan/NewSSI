import {
  CurrentMessageFIFO,
  updateCurrentMessageFIFO,
} from "./currentMessageFIFO";
import { ChatRunActiveError } from "@/lib/api/domains/chat/resumableChatStream";

async function* packets(items: unknown[], error?: Error) {
  for (const item of items) yield item as never;
  if (error) throw error;
}

it("pumps every packet and completes", async () => {
  const stack = new CurrentMessageFIFO();
  await updateCurrentMessageFIFO(stack, packets([{ a: 1 }, { b: 2 }]));
  expect([stack.nextPacket(), stack.nextPacket()]).toEqual([
    { a: 1 },
    { b: 2 },
  ]);
  expect(stack.isComplete).toBe(true);
});

it("keeps the typed error for the controller", async () => {
  const stack = new CurrentMessageFIFO();
  await updateCurrentMessageFIFO(
    stack,
    packets([], new ChatRunActiveError("busy"))
  );
  expect(stack.errorObject).toBeInstanceOf(ChatRunActiveError);
  expect(stack.error).toContain("still being generated");
});

describe("replay boundary", () => {
  const push = (stack: CurrentMessageFIFO, ...ids: number[]) =>
    ids.forEach((id) => stack.push({ id } as never));
  const pull = (stack: CurrentMessageFIFO) => {
    const packet = stack.nextPacket() as unknown as { id: number };
    return [packet.id, stack.replaying] as const;
  };

  it("is not replaying until told so", () => {
    const stack = new CurrentMessageFIFO();
    push(stack, 1);
    expect(pull(stack)).toEqual([1, false]);
  });

  it("flags exactly the packets pushed while replaying, however late they are pulled", () => {
    const stack = new CurrentMessageFIFO();
    stack.setReplaying(true);
    push(stack, 1, 2);
    stack.setReplaying(false);
    push(stack, 3, 4);
    // The consumer only starts after the producer is done: order still holds.
    expect([1, 2, 3, 4].map(() => pull(stack))).toEqual([
      [1, true],
      [2, true],
      [3, false],
      [4, false],
    ]);
  });

  it("follows the producer packet by packet when the consumer keeps up", () => {
    const stack = new CurrentMessageFIFO();
    stack.setReplaying(true);
    push(stack, 1);
    expect(pull(stack)).toEqual([1, true]);
    stack.setReplaying(false);
    push(stack, 2);
    expect(pull(stack)).toEqual([2, false]);
  });

  it("supports several replay windows (re-attach after a drop)", () => {
    const stack = new CurrentMessageFIFO();
    push(stack, 1);
    stack.setReplaying(true);
    push(stack, 2, 3);
    stack.setReplaying(false);
    push(stack, 4);
    stack.setReplaying(true);
    push(stack, 5);
    stack.setReplaying(false);
    push(stack, 6);
    expect([1, 2, 3, 4, 5, 6].map(() => pull(stack))).toEqual([
      [1, false],
      [2, true],
      [3, true],
      [4, false],
      [5, true],
      [6, false],
    ]);
  });

  it("ignores repeated changes to the same state", () => {
    const stack = new CurrentMessageFIFO();
    stack.setReplaying(true);
    stack.setReplaying(true);
    push(stack, 1);
    stack.setReplaying(false);
    stack.setReplaying(false);
    push(stack, 2);
    expect([pull(stack), pull(stack)]).toEqual([
      [1, true],
      [2, false],
    ]);
  });

  it("stays replaying for a packet whose replay ends right after it", () => {
    const stack = new CurrentMessageFIFO();
    stack.setReplaying(true);
    push(stack, 1);
    stack.setReplaying(false);
    // The last replayed packet is still a replayed packet.
    expect(pull(stack)).toEqual([1, true]);
    expect(stack.isEmpty()).toBe(true);
  });

  it("carries the flag through updateCurrentMessageFIFO from a stream", async () => {
    const stack = new CurrentMessageFIFO();
    async function* source() {
      stack.setReplaying(true);
      yield { id: 1 } as never;
      yield { id: 2 } as never;
      stack.setReplaying(false);
      yield { id: 3 } as never;
    }
    await updateCurrentMessageFIFO(stack, source());
    expect([pull(stack), pull(stack), pull(stack)]).toEqual([
      [1, true],
      [2, true],
      [3, false],
    ]);
  });

  it("reports whether the source itself is still replaying, ahead of the consumer", () => {
    const stack = new CurrentMessageFIFO();
    expect(stack.sourceReplaying).toBe(false);
    stack.setReplaying(true);
    push(stack, 1);
    expect(stack.sourceReplaying).toBe(true);
    stack.setReplaying(false);
    // The consumer has not pulled anything yet; the source is already live.
    expect(stack.sourceReplaying).toBe(false);
    expect(stack.replaying).toBe(false);
    expect(pull(stack)).toEqual([1, true]);
  });
});
