import type { Project } from "@/app/app/projects/projectsService";
import { ChatSessionSharedStatus } from "@/app/app/interfaces";
import { resolveCurrentProjectId } from "@/lib/projects/resolveProjectContext";

function makeProject(id: number, chatIds: string[]): Project {
  return {
    id,
    name: `Project ${id}`,
    description: null,
    created_at: "2026-07-30T10:00:00Z",
    user_id: "user-1",
    instructions: null,
    chat_sessions: chatIds.map((chatId) => ({
      id: chatId,
      name: `Chat ${chatId}`,
      persona_id: 0,
      time_created: "2026-07-30T10:00:00Z",
      time_updated: "2026-07-30T11:00:00Z",
      shared_status: ChatSessionSharedStatus.Private,
      project_id: id,
      current_alternate_model: "",
      current_temperature_override: null,
    })),
  };
}

describe("resolveCurrentProjectId", () => {
  it("uses the explicit project id when the page is focused on a project", () => {
    expect(
      resolveCurrentProjectId({
        projectIdParam: "42",
        chatId: "chat-123",
        projects: [makeProject(7, ["chat-123"])],
      })
    ).toBe(42);
  });

  it("finds the project that owns the active chat when no project id is in the URL", () => {
    expect(
      resolveCurrentProjectId({
        projectIdParam: null,
        chatId: "chat-123",
        projects: [makeProject(7, []), makeProject(42, ["chat-123"])],
      })
    ).toBe(42);
  });

  it("does not resolve a project for ungrouped chats", () => {
    expect(
      resolveCurrentProjectId({
        projectIdParam: null,
        chatId: "chat-123",
        projects: [makeProject(7, ["chat-456"])],
      })
    ).toBeNull();
  });
});
