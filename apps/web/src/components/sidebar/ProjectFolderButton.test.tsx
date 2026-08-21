import { render, screen } from "@tests/setup/test-utils";
import ProjectFolderButton from "@/sections/sidebar/ProjectFolderButton";
import { ChatSessionSharedStatus } from "@/app/app/interfaces";
import type { Project } from "@/app/app/projects/projectsService";
import { DRAG_TYPES } from "@/sections/sidebar/constants";

let mockIsOver = false;
let mockActive: any = null;

jest.mock("@dnd-kit/core", () => ({
  useDroppable: () => ({
    setNodeRef: jest.fn(),
    isOver: mockIsOver,
  }),
  useDndContext: () => ({
    active: mockActive,
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
  beforeEach(() => {
    mockIsOver = false;
    mockActive = null;
  });

  it("marks the containing project active when one of its chats is active", () => {
    const { container } = render(<ProjectFolderButton project={project} />);

    expect(screen.getAllByText("Launch planning")).toHaveLength(2);
    expect(container.querySelector("[data-state=\"active\"]")).not.toBeNull();
    expect(screen.queryByTestId("project-drop-zone")).toBeNull();
  });

  it("displays the dashed drop-target box when dragging a chat over a different project", () => {
    mockIsOver = true;
    mockActive = {
      data: {
        current: {
          type: DRAG_TYPES.CHAT,
          projectId: null,
        },
      },
    };

    render(<ProjectFolderButton project={project} />);

    const dropZone = screen.getByTestId("project-drop-zone");
    expect(dropZone).toBeInTheDocument();
    expect(dropZone.className).toContain("border-dashed");
  });

  it("does not display the drop-target box when dragging a chat from the same project", () => {
    mockIsOver = true;
    mockActive = {
      data: {
        current: {
          type: DRAG_TYPES.CHAT,
          projectId: 42,
        },
      },
    };

    render(<ProjectFolderButton project={project} />);

    expect(screen.queryByTestId("project-drop-zone")).toBeNull();
  });
});
