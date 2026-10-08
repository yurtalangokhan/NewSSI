import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { ReasoningRenderer } from "@/app/app/message/messageComponents/timeline/renderers/reasoning/ReasoningRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  PacketType,
  ReasoningPacket,
} from "@/lib/api/domains/chat/streaming-types";

const PLACEMENT = { turn_index: 0, tab_index: 0 };

function deltaPacket(reasoning: string): ReasoningPacket {
  return {
    placement: PLACEMENT,
    obj: { type: PacketType.REASONING_DELTA, reasoning },
  };
}

function endPacket(): ReasoningPacket {
  return {
    placement: PLACEMENT,
    obj: { type: PacketType.SECTION_END } as any,
  };
}

function reasoningElement(packets: ReasoningPacket[], stopPacketSeen: boolean) {
  return (
    <ReasoningRenderer
      packets={packets}
      state={{} as any}
      onComplete={jest.fn()}
      renderType={RenderType.FULL}
      animate={false}
      stopPacketSeen={stopPacketSeen}
    >
      {(results) => (
        <>
          {results.map((r, i) => (
            <div key={i}>{r.content}</div>
          ))}
        </>
      )}
    </ReasoningRenderer>
  );
}

describe("ReasoningRenderer mermaid streaming", () => {
  const FENCE = "```mermaid\nflowchart LR\n  A --> B";

  it("keeps an open fence pending while reasoning is still streaming", () => {
    renderWithI18n(reasoningElement([deltaPacket(FENCE)], false));

    expect(screen.getByTestId("mermaid-pending")).toBeInTheDocument();
    expect(screen.queryByTestId("mermaid-svg")).not.toBeInTheDocument();
  });

  it("renders the diagram once reasoning has stopped", async () => {
    const { rerender } = renderWithI18n(
      reasoningElement([deltaPacket(FENCE)], false)
    );
    expect(screen.getByTestId("mermaid-pending")).toBeInTheDocument();

    rerender(
      reasoningElement([deltaPacket(FENCE + "[Belge]\n```"), endPacket()], true)
    );

    await screen.findByTestId("mermaid-svg");
  });
});
