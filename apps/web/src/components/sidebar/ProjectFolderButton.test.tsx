import { render, screen } from "@tests/setup/test-utils";
import ProjectFolderButton from "@/sections/sidebar/ProjectFolderButton";
import { ChatSessionSharedStatus } from "@/app/app/interfaces";
import type { Project } from "@/app/app/projects/projectsService";

jest.mock("@dnd-kit/core", () => ({
  useDroppable: () => ({
    setNodeRef: jest.fn(),
    isOver: false,
  }),
}));

jest.mock("@/hooks/appNavigation", () => ({
  useAppRouter: () => jest.fn(),
}));

jest.mock("@/hooks/useAppFocus", () => ({
  __esModule: true,
  default: () => ({
    isProject: () => false,
    isChat: () => true,
    getId: () => "chat-123",
  }),
}));

jest.mock("@/providers/ProjectsContext", () => ({
  useProjectsContext: () => ({
    currentProjectId: 42,
    renameProject: jest.fn(),
    deleteProject: jest.fn(),
  }),
}));

jest.mock("@/sections/sidebar/ChatButton", () => ({
  __esModule: true,
  default: () => null,
}));

const project: Project = {
  id: 42,
  name: "Launch planning",
  description: null,
  created_at: "2026-07-30T10:00:00Z",
  user_id: "user-1",
  instructions: null,
  chat_sessions: [
    {
      id: "chat-123",
      name: "Roadmap notes",
      persona_id: 0,
      time_created: "2026-07-30T10:00:00Z",
      time_updated: "2026-07-30T11:00:00Z",
      shared_status: ChatSessionSharedStatus.Private,
      project_id: 42,
      current_alternate_model: "",
      current_temperature_override: null,
    },
  ],
};

describe("ProjectFolderButton", () => {
  it("marks the containing project active when one of its chats is active", () => {
    const { container } = render(<ProjectFolderButton project={project} />);

    expect(screen.getAllByText("Launch planning")).toHaveLength(2);
    expect(container.querySelector('[data-state="active"]')).not.toBeNull();
  });
});
