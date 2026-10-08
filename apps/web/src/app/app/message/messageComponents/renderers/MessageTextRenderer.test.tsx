import { act, screen, waitFor } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { MessageTextRenderer } from "@/app/app/message/messageComponents/renderers/MessageTextRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import { PacketType, ChatPacket } from "@/lib/api/domains/chat/streaming-types";

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({
    hasBackground: false,
    foregroundTextClass: "",
    foregroundTextStyle: {},
    foregroundMutedTextClass: "",
    foregroundMutedTextStyle: {},
  }),
}));

const PLACEMENT = { turn_index: 0, tab_index: 0 };

function deltaPacket(content: string): ChatPacket {
  return {
    placement: PLACEMENT,
    obj: { type: PacketType.MESSAGE_DELTA, content } as any,
  };
}

describe("MessageTextRenderer isRevealing", () => {
  // stop has arrived (stopPacketSeen=true) but the reveal animation (animate=true)
  // has only shown the first packet: the fence's real end is still hidden, so
  // Mermaid must stay pending even though there is no more text coming.
  const packets = [
    deltaPacket("```mermaid\nflowchart LR\n  A --> B"),
    deltaPacket("[Belge]\n```"),
    deltaPacket("\n\nSonra"),
  ];

  it("keeps the diagram pending while the reveal is still catching up after stop", () => {
    renderWithI18n(
      <MessageTextRenderer
        packets={packets}
        state={{} as any}
        onComplete={jest.fn()}
        renderType={RenderType.FULL}
        animate
        stopPacketSeen
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );

    expect(screen.getByTestId("mermaid-pending")).toBeInTheDocument();
    expect(screen.queryByTestId("mermaid-svg")).not.toBeInTheDocument();
  });

  it("renders the diagram once the reveal catches up", async () => {
    renderWithI18n(
      <MessageTextRenderer
        packets={packets}
        state={{} as any}
        onComplete={jest.fn()}
        renderType={RenderType.FULL}
        animate
        stopPacketSeen
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );

    await waitFor(
      () => expect(screen.getByTestId("mermaid-svg")).toBeInTheDocument(),
      {
        timeout: 3000,
      }
    );
  });
});

describe("MessageTextRenderer replayed packets", () => {
  const replayed = (content: string): ChatPacket => ({
    ...deltaPacket(content),
    replayed: true,
  });
  const words = ["Alpha ", "Beta ", "Gamma ", "Delta "];

  const renderText = (packets: ChatPacket[], animate = true) =>
    renderWithI18n(
      <MessageTextRenderer
        packets={packets}
        state={{} as any}
        onComplete={jest.fn()}
        renderType={RenderType.FULL}
        animate={animate}
        stopPacketSeen={false}
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );

  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  it("still types live packets from the first one (unchanged behavior)", () => {
    renderText(words.map(deltaPacket));
    expect(screen.getByText(/Alpha/)).toBeInTheDocument();
    expect(screen.queryByText(/Beta/)).not.toBeInTheDocument();
  });

  it("shows replayed packets at once instead of typing them", () => {
    renderText(words.map(replayed));
    expect(screen.getByText(/Alpha Beta Gamma Delta/)).toBeInTheDocument();
  });

  it("shows the replayed prefix at once and types only what follows it", () => {
    renderText([
      replayed(words[0]!),
      replayed(words[1]!),
      deltaPacket(words[2]!),
      deltaPacket(words[3]!),
    ]);
    expect(screen.getByText(/Alpha Beta/)).toBeInTheDocument();
    expect(screen.queryByText(/Gamma/)).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(10);
    });
    expect(screen.getByText(/Alpha Beta Gamma/)).toBeInTheDocument();
    expect(screen.queryByText(/Delta/)).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(10);
    });
    expect(screen.getByText(/Alpha Beta Gamma Delta/)).toBeInTheDocument();
  });

  it("does not replay the typing when live packets arrive after a replay", () => {
    const backlog = [replayed(words[0]!), replayed(words[1]!)];
    const { rerender } = renderText(backlog);
    expect(screen.getByText(/Alpha Beta/)).toBeInTheDocument();

    rerender(
      <MessageTextRenderer
        packets={[...backlog, deltaPacket(words[2]!)]}
        state={{} as any}
        onComplete={jest.fn()}
        renderType={RenderType.FULL}
        animate
        stopPacketSeen={false}
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );
    // The backlog stays put; only the new packet is revealed on its own tick.
    expect(screen.getByText(/Alpha Beta/)).toBeInTheDocument();
    expect(screen.queryByText(/Gamma/)).not.toBeInTheDocument();
    act(() => {
      jest.advanceTimersByTime(10);
    });
    expect(screen.getByText(/Alpha Beta Gamma/)).toBeInTheDocument();
  });

  it("jumps ahead when a replay lands on a text that had already started typing", () => {
    const first = deltaPacket(words[0]!);
    const { rerender } = renderText([first]);
    expect(screen.getByText(/Alpha/)).toBeInTheDocument();

    const catchUp = [
      { ...first, replayed: true },
      replayed(words[1]!),
      replayed(words[2]!),
    ];
    rerender(
      <MessageTextRenderer
        packets={catchUp}
        state={{} as any}
        onComplete={jest.fn()}
        renderType={RenderType.FULL}
        animate
        stopPacketSeen={false}
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );
    expect(screen.getByText(/Alpha Beta Gamma/)).toBeInTheDocument();
  });

  it("completes only once the live part has been revealed too", () => {
    const onComplete = jest.fn();
    const stop = {
      placement: PLACEMENT,
      obj: { type: PacketType.MESSAGE_END } as any,
    };
    renderWithI18n(
      <MessageTextRenderer
        packets={[replayed(words[0]!), deltaPacket(words[1]!), stop]}
        state={{} as any}
        onComplete={onComplete}
        renderType={RenderType.FULL}
        animate
        stopPacketSeen
      >
        {(results) => (
          <>
            {results.map((r, i) => (
              <div key={i}>{r.content}</div>
            ))}
          </>
        )}
      </MessageTextRenderer>
    );
    expect(onComplete).not.toHaveBeenCalled();
    // One tick per packet still to reveal; each needs its own render in between.
    act(() => {
      jest.advanceTimersByTime(10);
    });
    expect(onComplete).not.toHaveBeenCalled();
    act(() => {
      jest.advanceTimersByTime(10);
    });
    expect(onComplete).toHaveBeenCalled();
  });
});
