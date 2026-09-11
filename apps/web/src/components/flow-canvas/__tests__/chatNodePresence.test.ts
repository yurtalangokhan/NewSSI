import {
  getChatNodePresence,
  hasRequiredChatNodes,
} from "../utils/chatNodePresence";

const node = (type: string) => ({ data: { type } });

describe("getChatNodePresence", () => {
  it("reports neither for an empty canvas", () => {
    expect(getChatNodePresence([])).toEqual({
      hasChatInput: false,
      hasChatOutput: false,
    });
  });

  it("detects a ChatInput node", () => {
    expect(getChatNodePresence([node("ChatInput"), node("Model")])).toEqual({
      hasChatInput: true,
      hasChatOutput: false,
    });
  });

  it("detects a ChatOutput node", () => {
    expect(getChatNodePresence([node("Model"), node("ChatOutput")])).toEqual({
      hasChatInput: false,
      hasChatOutput: true,
    });
  });

  it("detects both when present", () => {
    expect(
      getChatNodePresence([
        node("ChatInput"),
        node("Model"),
        node("ChatOutput"),
      ])
    ).toEqual({ hasChatInput: true, hasChatOutput: true });
  });

  it("tolerates nodes without a data.type", () => {
    expect(
      getChatNodePresence([{}, { data: undefined }, node("ChatInput")])
    ).toEqual({ hasChatInput: true, hasChatOutput: false });
  });
});

describe("hasRequiredChatNodes", () => {
  it("is true only when both a chat entry and exit exist", () => {
    expect(hasRequiredChatNodes([])).toBe(false);
    expect(hasRequiredChatNodes([node("ChatInput")])).toBe(false);
    expect(hasRequiredChatNodes([node("ChatOutput")])).toBe(false);
    expect(hasRequiredChatNodes([node("ChatInput"), node("ChatOutput")])).toBe(
      true
    );
  });
});
