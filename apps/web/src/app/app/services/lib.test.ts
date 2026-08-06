import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { ReadonlyURLSearchParams } from "next/navigation";
import { buildChatUrl } from "./lib";

describe("buildChatUrl", () => {
  it("uses path routes for chat sessions and omits app state query params", () => {
    const existingSearchParams = new URLSearchParams({
      [SEARCH_PARAM_NAMES.PERSONA_ID]: "42",
      [SEARCH_PARAM_NAMES.PROJECT_ID]: "9",
      [SEARCH_PARAM_NAMES.USER_PROMPT]: "hello",
      keep: "this",
    }) as unknown as ReadonlyURLSearchParams;

    expect(buildChatUrl(existingSearchParams, "chat-1", 42, false, true)).toBe(
      "/app/chats/chat-1?keep=this"
    );
  });

  it("keeps search route query behavior for search sessions", () => {
    expect(buildChatUrl(null, "search-1", null, true, false)).toBe(
      "/app?searchId=search-1"
    );
  });
});
