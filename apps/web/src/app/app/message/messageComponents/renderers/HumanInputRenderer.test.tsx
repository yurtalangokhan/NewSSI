import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import { HumanInputRenderer } from "@/app/app/message/messageComponents/renderers/HumanInputRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  HumanInputPacket,
  HumanInputRequest,
  PacketType,
} from "@/app/app/services/streamingModels";

// Minimal i18next stand-in (same shape as GeneratedFileRenderer.test.tsx).
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (
      key: string,
      fallback?: string | Record<string, unknown>,
      opts?: Record<string, unknown>
    ) => {
      const template =
        typeof fallback === "string" ? fallback : String(fallback ?? key);
      return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
        String((opts ?? {})[name] ?? "")
      );
    },
  }),
}));

const PLACEMENT = { turn_index: 0, tab_index: 0 };

function requestPacket(
  overrides: Partial<HumanInputRequest> = {}
): HumanInputPacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.HUMAN_INPUT,
      node_id: "hi-1",
      prompt: "Bu gönderi taslağı için ne yapalım?",
      decisions: ["yayinla", "revize", "iptal"],
      ...overrides,
    } as HumanInputRequest,
  };
}

function renderRequest(
  packets: HumanInputPacket[],
  state: Record<string, unknown> = {}
) {
  return render(
    <HumanInputRenderer
      packets={packets}
      state={state as any}
      onComplete={jest.fn()}
      renderType={RenderType.FULL}
      animate={false}
      stopPacketSeen={false}
    >
      {(results) => (
        <>
          {results.map((r, i) => (
            <div key={i}>{r.content}</div>
          ))}
        </>
      )}
    </HumanInputRenderer>
  );
}

describe("HumanInputRenderer", () => {
  test("renders the node's prompt and one button per declared action", () => {
    renderRequest([requestPacket()]);

    expect(
      screen.getByText("Bu gönderi taslağı için ne yapalım?")
    ).toBeInTheDocument();
    for (const label of ["yayinla", "revize", "iptal"]) {
      expect(
        screen.getByTestId(`human-input-decision-${label}`)
      ).toBeInTheDocument();
    }
  });

  test("clicking an action sends that label back as the resume", async () => {
    const onHumanDecision = jest.fn();
    renderRequest([requestPacket()], { onHumanDecision });

    await userEvent.click(screen.getByTestId("human-input-decision-revize"));

    expect(onHumanDecision).toHaveBeenCalledTimes(1);
    expect(onHumanDecision).toHaveBeenCalledWith("revize");
  });

  test("the buttons lock after a choice so a second click is not a new turn", async () => {
    const onHumanDecision = jest.fn();
    renderRequest([requestPacket()], { onHumanDecision });

    await userEvent.click(screen.getByTestId("human-input-decision-yayinla"));
    await userEvent.click(screen.getByTestId("human-input-decision-iptal"));

    expect(onHumanDecision).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("human-input-picked")).toHaveTextContent(
      "yayinla"
    );
  });

  test("a send already in flight locks the buttons too", async () => {
    const onHumanDecision = jest.fn();
    renderRequest([requestPacket()], { onHumanDecision, isStreaming: true });

    await userEvent.click(screen.getByTestId("human-input-decision-yayinla"));

    expect(onHumanDecision).not.toHaveBeenCalled();
  });

  test("blank action labels are dropped", () => {
    renderRequest([requestPacket({ decisions: ["onayla", "", "   "] })]);

    expect(
      screen.getByTestId("human-input-decision-onayla")
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  test("renders nothing when the group carries no request packet", () => {
    const { container } = renderRequest([]);
    expect(
      container.querySelector("[data-testid='human-input-request']")
    ).toBeNull();
  });
});
