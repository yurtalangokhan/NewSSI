import { AppFocus } from "@/hooks/useAppFocus";
import type { AppFocusValue } from "@/hooks/appNavigation";

describe("AppFocus.showsChatBackground", () => {
  it.each<[string, AppFocusValue, boolean]>([
    ["a chat", { type: "chat", id: "c1" }, true],
    ["an agent", { type: "agent", id: "1" }, true],
    ["a new session", "new-session", true],
    ["a project", { type: "project", id: "1" }, false],
    ["a shared chat", "shared-chat", false],
    ["the agents list", "more-agents", false],
    ["user settings", "user-settings", false],
  ])("for %s is %s", (_name, value, expected) => {
    expect(new AppFocus(value).showsChatBackground()).toBe(expected);
  });
});
