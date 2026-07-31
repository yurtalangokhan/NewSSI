import type { Project } from "@/app/app/projects/projectsService";

interface ResolveCurrentProjectIdParams {
  projectIdParam: string | null;
  chatId: string | null;
  projects: Project[];
}

export function resolveCurrentProjectId({
  projectIdParam,
  chatId,
  projects,
}: ResolveCurrentProjectIdParams): number | null {
  if (projectIdParam) {
    const explicitProjectId = Number.parseInt(projectIdParam, 10);
    return Number.isNaN(explicitProjectId) ? null : explicitProjectId;
  }

  if (!chatId) {
    return null;
  }

  return (
    projects.find((project) =>
      project.chat_sessions.some((chatSession) => chatSession.id === chatId)
    )?.id ?? null
  );
}
