import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import { UserClarificationRenderer } from "@/app/app/message/messageComponents/renderers/UserClarificationRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  ClarificationQuestion,
  PacketType,
  UserClarificationPacket,
} from "@/app/app/services/streamingModels";

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

const AUDIENCE: ClarificationQuestion = {
  question: "Raporu kim okuyacak?",
  header: "Hedef kitle",
  options: [
    { label: "Yönetim", description: "Özet, sayılar, karar önerisi" },
    { label: "Teknik ekip", description: "Detay, metodoloji, ham veri" },
  ],
};

const FORMAT: ClarificationQuestion = {
  question: "Hangi biçimde olsun?",
  header: "Biçim",
  options: [{ label: "Kısa" }, { label: "Uzun" }],
};

function card(
  questions: ClarificationQuestion[] = [AUDIENCE],
  overrides: Record<string, unknown> = {}
): UserClarificationPacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.USER_CLARIFICATION,
      v: 1,
      request_id: "i1",
      questions,
      agent_path: [],
      ...overrides,
    },
  } as UserClarificationPacket;
}

function lock(
  overrides: Record<string, unknown> = {}
): UserClarificationPacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.USER_CLARIFICATION_ANSWERED,
      v: 1,
      request_id: "i1",
      answered: true,
      answers: { "Hedef kitle": ["Yönetim"] },
      ...overrides,
    },
  } as UserClarificationPacket;
}

function renderCard(
  packets: UserClarificationPacket[],
  state: Record<string, unknown> = {}
) {
  return render(
    <UserClarificationRenderer
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
    </UserClarificationRenderer>
  );
}

describe("UserClarificationRenderer", () => {
  test("a single question needs no tabs", () => {
    renderCard([card()]);

    expect(screen.getByText("Raporu kim okuyacak?")).toBeInTheDocument();
    expect(
      screen.getByText("Özet, sayılar, karar önerisi")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("user-clarification-tabs")).toBeNull();
  });

  test("several questions get a tab strip titled by their headers", () => {
    renderCard([card([AUDIENCE, FORMAT])]);

    expect(screen.getByTestId("user-clarification-tabs")).toBeInTheDocument();
    expect(
      screen.getByTestId("user-clarification-tab-Hedef kitle")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("user-clarification-tab-Biçim")
    ).toBeInTheDocument();
    expect(screen.getByTestId("user-clarification-progress")).toHaveTextContent(
      "0/2"
    );
  });

  test("a single-choice answer moves on by itself", async () => {
    const user = userEvent.setup();
    renderCard([card([AUDIENCE, FORMAT])]);

    await user.click(screen.getByTestId("user-clarification-option-Yönetim"));

    // The second question is now the one on screen — no extra click spent.
    expect(screen.getByText("Hangi biçimde olsun?")).toBeInTheDocument();
    expect(screen.getByTestId("user-clarification-progress")).toHaveTextContent(
      "1/2"
    );
  });

  test("answering the last question sends everything in one go", async () => {
    const user = userEvent.setup();
    const onClarificationAnswer = jest.fn();
    renderCard([card([AUDIENCE, FORMAT])], { onClarificationAnswer });

    await user.click(screen.getByTestId("user-clarification-option-Yönetim"));
    await user.click(screen.getByTestId("user-clarification-option-Kısa"));

    expect(onClarificationAnswer).toHaveBeenCalledTimes(1);
    expect(onClarificationAnswer).toHaveBeenCalledWith({
      answered: true,
      answers: { "Hedef kitle": ["Yönetim"], Biçim: ["Kısa"] },
    });
  });

  test("a multi-select waits for Continue and refuses an empty answer", async () => {
    const user = userEvent.setup();
    const onClarificationAnswer = jest.fn();
    renderCard([card([{ ...FORMAT, multiSelect: true }])], {
      onClarificationAnswer,
    });

    expect(screen.getByTestId("user-clarification-continue")).toBeDisabled();

    await user.click(screen.getByTestId("user-clarification-option-Kısa"));
    await user.click(screen.getByTestId("user-clarification-option-Uzun"));
    expect(onClarificationAnswer).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("user-clarification-continue"));
    expect(onClarificationAnswer).toHaveBeenCalledWith({
      answered: true,
      answers: { Biçim: ["Kısa", "Uzun"] },
    });
  });

  test("a tab can be revisited and its answer changed", async () => {
    const user = userEvent.setup();
    const onClarificationAnswer = jest.fn();
    renderCard([card([AUDIENCE, FORMAT])], { onClarificationAnswer });

    await user.click(screen.getByTestId("user-clarification-option-Yönetim"));
    await user.click(screen.getByTestId("user-clarification-tab-Hedef kitle"));
    await user.click(
      screen.getByTestId("user-clarification-option-Teknik ekip")
    );
    await user.click(screen.getByTestId("user-clarification-option-Kısa"));

    expect(onClarificationAnswer).toHaveBeenCalledWith({
      answered: true,
      answers: { "Hedef kitle": ["Teknik ekip"], Biçim: ["Kısa"] },
    });
  });

  test("'you decide' is offered by the card, not by the model", async () => {
    const user = userEvent.setup();
    const onClarificationAnswer = jest.fn();
    renderCard([card()], { onClarificationAnswer });

    await user.click(screen.getByTestId("user-clarification-defer"));

    expect(onClarificationAnswer).toHaveBeenCalledWith({
      answered: true,
      answers: { "Hedef kitle": [] },
    });
  });

  test("an answered card is a record, not a second chance", () => {
    renderCard([card(), lock()]);

    expect(
      screen.getByTestId("user-clarification-option-Yönetim")
    ).toBeDisabled();
    expect(
      screen.getByTestId("user-clarification-option-Yönetim")
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByTestId("user-clarification-defer")).toBeNull();
  });

  test("a card answered by typing says so", () => {
    renderCard([
      card(),
      lock({ answered: false, answers: undefined, text: "boşver" }),
    ]);

    expect(
      screen.getByTestId("user-clarification-skipped")
    ).toBeInTheDocument();
  });

  test("a supervisor's question says which sub-agent is asking", () => {
    renderCard([card([AUDIENCE], { agent_path: ["Destek", "Fatura Uzmanı"] })]);

    expect(screen.getByText("Fatura Uzmanı soruyor")).toBeInTheDocument();
  });

  test("an unknown version says so instead of guessing at the controls", () => {
    renderCard([card([AUDIENCE], { v: 99 })]);

    expect(
      screen.getByTestId("user-clarification-unsupported")
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("user-clarification-option-Yönetim")
    ).toBeNull();
  });

  test("a run still streaming cannot be answered twice", () => {
    renderCard([card()], { isStreaming: true });

    expect(
      screen.getByTestId("user-clarification-option-Yönetim")
    ).toBeDisabled();
  });
});
