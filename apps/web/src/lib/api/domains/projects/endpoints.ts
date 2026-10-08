import type { BackendTarget } from "@/lib/api/http/types";

export type ProjectId = number;

export type ChatSessionId = string;

export const projectsEndpoints = {
  getSessionFiles: (sessionId: ChatSessionId) =>
    ({
      method: "GET",
      browserPath: `/api/user/projects/session/${encodeURIComponent(
        sessionId
      )}/files`,
      backend: {
        service: "agent",
        path: `/api/v1/user/projects/session/${encodeURIComponent(
          sessionId
        )}/files`,
      },
    }) as const,
  getSessionTokenCount: (sessionId: ChatSessionId) =>
    ({
      method: "GET",
      browserPath: `/api/user/projects/session/${encodeURIComponent(
        sessionId
      )}/token-count`,
      backend: {
        service: "agent",
        path: `/api/v1/user/projects/session/${encodeURIComponent(
          sessionId
        )}/token-count`,
      },
    }) as const,
  listProjects: {
    method: "GET",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  },
  createProject: {
    method: "POST",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  },
  updateProject: {
    method: "PATCH",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  },
  deleteProject: {
    method: "DELETE",
    browserPath: "/api/user/projects",
    backend: { service: "agent", path: "/api/v1/user/projects" },
  },
  recentFiles: {
    method: "GET",
    browserPath: "/api/user/files/recent",
    backend: { service: "agent", path: "/api/v1/user/files/recent" },
  },
  projectCreate: { browserPath: "/api/user/projects/create" },
  createProjectWithName: (name: string): { browserPath: string } => {
    return {
      browserPath: `${
        projectsEndpoints.projectCreate.browserPath
      }?name=${encodeURIComponent(name)}`,
    };
  },
  projectDetail: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}`,
    };
  },
  projectInstructions: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}/instructions`,
    };
  },
  projectDetails: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}/details`,
    };
  },
  projectTokenCount: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}/token-count`,
    };
  },
  projectFilesCatalog: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/files/${encodeURIComponent(
        String(projectId)
      )}`,
    };
  },
  projectFiles: (
    projectId: ProjectId,
    fileId: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}/files/${encodeURIComponent(fileId)}`,
    };
  },
  moveChatSession: (projectId: ProjectId): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/${encodeURIComponent(
        String(projectId)
      )}/move_chat_session`,
    };
  },
  removeChatSession: { browserPath: "/api/user/projects/remove_chat_session" },
  projectFileUpload: { browserPath: "/api/user/projects/file/upload" },
  projectFileDelete: (fileId: string): { browserPath: string } => {
    return {
      browserPath: `/api/user/projects/file/${encodeURIComponent(fileId)}`,
    };
  },
  projectFileStatuses: { browserPath: "/api/user/projects/file/statuses" },
  path: (
    segments: string[]
  ): { backend: import("@/lib/api/http/types").BackendTarget } => ({
    backend: {
      service: "agent",
      path: `/api/v1/user/projects/${segments.join("/")}`,
    } as const satisfies BackendTarget,
  }),
} as const;
