import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import {
  buildAppPath,
  buildCanonicalAppPathFromSearch,
  parseAppFocus,
} from "@/hooks/appNavigation";

function searchParams(params: Record<string, string> = {}) {
  return new URLSearchParams(params);
}

describe("app navigation helpers", () => {
  it("builds path-based app routes", () => {
    expect(buildAppPath({ type: "new-session" })).toBe("/app");
    expect(buildAppPath({ type: "chat", id: "chat-1" })).toBe(
      "/app/chats/chat-1"
    );
    expect(buildAppPath({ type: "agent", id: 42 })).toBe("/app/agents/42");
    expect(buildAppPath({ type: "project", id: 9 })).toBe("/app/projects/9");
  });

  it("parses path-based app focus before legacy query params", () => {
    const focus = parseAppFocus(
      "/app/chats/chat-1",
      searchParams({ [SEARCH_PARAM_NAMES.PERSONA_ID]: "42" })
    );

    expect(focus).toEqual({ type: "chat", id: "chat-1" });
  });

  it("parses legacy app query params during migration", () => {
    expect(
      parseAppFocus(
        "/app",
        searchParams({ [SEARCH_PARAM_NAMES.CHAT_ID]: "chat-1" })
      )
    ).toEqual({ type: "chat", id: "chat-1" });
    expect(
      parseAppFocus(
        "/app",
        searchParams({ [SEARCH_PARAM_NAMES.PERSONA_ID]: "42" })
      )
    ).toEqual({ type: "agent", id: "42" });
    expect(
      parseAppFocus(
        "/app",
        searchParams({ [SEARCH_PARAM_NAMES.PROJECT_ID]: "9" })
      )
    ).toEqual({ type: "project", id: "9" });
  });

  it("keeps existing app utility pages out of agent focus", () => {
    expect(parseAppFocus("/app/agents", searchParams())).toBe("more-agents");
    expect(parseAppFocus("/app/agents/create", searchParams())).toBe(
      "more-agents"
    );
    expect(parseAppFocus("/app/agents/edit/42", searchParams())).toBe(
      "more-agents"
    );
    expect(parseAppFocus("/app/agents/42", searchParams())).toEqual({
      type: "agent",
      id: "42",
    });
  });

  it("builds canonical paths from legacy app query params", () => {
    expect(
      buildCanonicalAppPathFromSearch(
        searchParams({
          [SEARCH_PARAM_NAMES.CHAT_ID]: "chat-1",
          [SEARCH_PARAM_NAMES.PROJECT_ID]: "9",
          keep: "this",
        })
      )
    ).toBe("/app/chats/chat-1?keep=this");

    expect(
      buildCanonicalAppPathFromSearch(
        searchParams({
          [SEARCH_PARAM_NAMES.PERSONA_ID]: "42",
          [SEARCH_PARAM_NAMES.PROJECT_ID]: "9",
        })
      )
    ).toBe("/app/agents/42?projectId=9");

    expect(
      buildCanonicalAppPathFromSearch(
        searchParams({ [SEARCH_PARAM_NAMES.PROJECT_ID]: "9" })
      )
    ).toBe("/app/projects/9");

    expect(buildCanonicalAppPathFromSearch(searchParams())).toBeNull();
  });
});
