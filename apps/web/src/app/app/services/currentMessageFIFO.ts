import { PacketType } from "@/lib/api/domains/chat/message-types";

export class CurrentMessageFIFO {
  private stack: PacketType[] = [];
  isComplete: boolean = false;
  error: string | null = null;
  // The original thrown error, so the controller can branch on its type
  // (409 active-run, replay expired) without string-matching the message.
  errorObject: Error | null = null;

  private pushed = 0;
  private pulled = 0;
  // Replay changes as the producer made them, keyed by the number of packets
  // pushed before the change: the producer runs ahead of the consumer, so the
  // boundary has to travel with the packets rather than as a live flag.
  private producerReplaying = false;
  private transitions: { at: number; replaying: boolean }[] = [];
  private consumerReplaying = false;

  /** Whether the packet most recently returned by `nextPacket` was replayed history. */
  get replaying(): boolean {
    return this.consumerReplaying;
  }

  /** Whether the stream is replaying right now, however far the consumer has got. */
  get sourceReplaying(): boolean {
    return this.producerReplaying;
  }

  /** Producer side: the packets pushed from now on are (or are no longer) replay. */
  setReplaying(replaying: boolean) {
    if (replaying === this.producerReplaying) return;
    this.producerReplaying = replaying;
    this.transitions.push({ at: this.pushed, replaying });
  }

  push(packetBunch: PacketType) {
    this.stack.push(packetBunch);
    this.pushed += 1;
  }

  nextPacket(): PacketType | undefined {
    const packet = this.stack.shift();
    if (packet === undefined) return undefined;
    // A change applies to the packet at index `at` and every one after it.
    for (
      let next = this.transitions[0];
      next !== undefined && next.at <= this.pulled;
      next = this.transitions[0]
    ) {
      this.consumerReplaying = next.replaying;
      this.transitions.shift();
    }
    this.pulled += 1;
    return packet;
  }

  isEmpty(): boolean {
    return this.stack.length === 0;
  }
}

export async function updateCurrentMessageFIFO(
  stack: CurrentMessageFIFO,
  source: AsyncIterable<PacketType>,
  signal?: AbortSignal
) {
  try {
    for await (const packet of source) {
      if (signal?.aborted) {
        throw new Error("AbortError");
      }
      stack.push(packet);
    }
  } catch (error: unknown) {
    if (error instanceof Error) {
      if (error.name === "AbortError") {
        console.debug("Stream aborted");
      } else {
        stack.error = error.message;
        stack.errorObject = error;
      }
    } else {
      stack.error = String(error);
      stack.errorObject = new Error(String(error));
    }
  } finally {
    stack.isComplete = true;
  }
}
