import { ApiRequestError, parseApiErrorResponse } from "@/lib/api/errors";
import { agentServicePayloadResponse } from "@/lib/api/agentServiceResponse";
import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";
import { apiRequest } from "@/lib/api/http/browser";
import type {
  Project,
  UserFileDeleteResult,
  ProjectDetails,
  CategorizedFiles,
  ProjectFile,
} from "@/lib/api/domains/projects/types";

import type {
  ChatSessionId,
  ProjectId,
} from "@/lib/api/domains/projects/endpoints";

async function handleRequestError(
  _action: string,
  response: Response
): Promise<never> {
  throw new ApiRequestError(await parseApiErrorResponse(response));
}

async function requestProjectJson<T>(
  path: string,
  action: string,
  options?: RequestInit
): Promise<T> {
  const response = await apiRequest(path, options).then(
    agentServicePayloadResponse
  );
  if (!response.ok) {
    await handleRequestError(action, response);
  }
  return response.json() as Promise<T>;
}

async function requestProjectRaw(
  path: string,
  action: string,
  options?: RequestInit
): Promise<Response> {
  const response = await apiRequest(path, options).then(
    agentServicePayloadResponse
  );
  if (!response.ok) {
    await handleRequestError(action, response);
  }
  return response;
}

export function fetchProjectCatalog(): Promise<Project[]> {
  return requestProjectJson(
    projectsEndpoints.listProjects.browserPath,
    "Fetch projects"
  );
}

export function createProject(name: string): Promise<Project> {
  return requestProjectJson(
    projectsEndpoints.createProjectWithName(name).browserPath,
    "Create project",
    {
      method: "POST",
    }
  );
}

export function renameProject(
  projectId: ProjectId,
  name: string
): Promise<Project> {
  return requestProjectJson(
    projectsEndpoints.projectDetail(projectId).browserPath,
    "Rename project",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }
  );
}

export async function deleteProject(projectId: ProjectId): Promise<void> {
  await requestProjectRaw(
    projectsEndpoints.projectDetail(projectId).browserPath,
    "Delete project",
    {
      method: "DELETE",
    }
  );
}

export async function upsertProjectInstructions(
  projectId: ProjectId,
  instructions: string
): Promise<string | null> {
  const data = await requestProjectJson<{ instructions: string | null }>(
    projectsEndpoints.projectInstructions(projectId).browserPath,
    "Update project instructions",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instructions }),
    }
  );
  return data.instructions ?? null;
}

export function fetchProjectDetails(
  projectId: ProjectId
): Promise<ProjectDetails> {
  return requestProjectJson(
    projectsEndpoints.projectDetails(projectId).browserPath,
    "Fetch project details"
  );
}

export async function fetchProjectTokenCount(
  projectId: ProjectId
): Promise<number> {
  const response = await apiRequest(
    projectsEndpoints.projectTokenCount(projectId).browserPath
  ).then(agentServicePayloadResponse);
  if (!response.ok) {
    return 0;
  }
  const data = (await response.json()) as { total_tokens?: number };
  return data.total_tokens ?? 0;
}

// Upload response contracts are owned by projects/types.ts.

export async function uploadFiles(
  files: File[],
  projectId?: ProjectId | null,
  tempIdMap?: Map<string, string>
): Promise<CategorizedFiles> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (projectId !== undefined && projectId !== null) {
    formData.append("project_id", String(projectId));
  }
  if (tempIdMap !== undefined && tempIdMap !== null) {
    formData.append(
      "temp_id_map",
      JSON.stringify(Object.fromEntries(tempIdMap))
    );
  }

  const response = await apiRequest(
    projectsEndpoints.projectFileUpload.browserPath,
    {
      method: "POST",
      body: formData,
    }
  ).then(agentServicePayloadResponse);
  if (!response.ok) {
    const errorData = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      errorData?.detail || `Upload files failed (Status: ${response.status})`
    );
  }
  return response.json() as Promise<CategorizedFiles>;
}

export function getRecentFiles(): Promise<ProjectFile[]> {
  return requestProjectJson(
    projectsEndpoints.recentFiles.browserPath,
    "Fetch recent files"
  );
}

export function getFilesInProject(
  projectId: ProjectId
): Promise<ProjectFile[]> {
  return requestProjectJson(
    projectsEndpoints.projectFilesCatalog(projectId).browserPath,
    "Fetch project files"
  );
}

export function unlinkFileFromProject(
  projectId: ProjectId,
  fileId: string
): Promise<Response> {
  return requestProjectRaw(
    projectsEndpoints.projectFiles(projectId, fileId).browserPath,
    "Unlink file from project",
    { method: "DELETE" }
  );
}

export function linkFileToProject(
  projectId: ProjectId,
  fileId: string
): Promise<Response> {
  return requestProjectRaw(
    projectsEndpoints.projectFiles(projectId, fileId).browserPath,
    "Link file to project",
    { method: "POST" }
  );
}

export function deleteUserFile(fileId: string): Promise<UserFileDeleteResult> {
  return requestProjectJson(
    projectsEndpoints.projectFileDelete(fileId).browserPath,
    "Delete file",
    {
      method: "DELETE",
    }
  );
}

export function getUserFileStatuses(fileIds: string[]): Promise<ProjectFile[]> {
  return requestProjectJson(
    projectsEndpoints.projectFileStatuses.browserPath,
    "Fetch file statuses",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_ids: fileIds }),
    }
  );
}

export async function getSessionProjectTokenCount(
  chatSessionId: ChatSessionId
): Promise<number> {
  const response = await apiRequest(
    projectsEndpoints.getSessionTokenCount(chatSessionId).browserPath
  ).then(agentServicePayloadResponse);
  if (!response.ok) {
    return 0;
  }
  const data = (await response.json()) as { total_tokens?: number };
  return data.total_tokens ?? 0;
}

export async function getProjectFilesForSession(
  chatSessionId: ChatSessionId
): Promise<ProjectFile[]> {
  const response = await apiRequest(
    projectsEndpoints.getSessionFiles(chatSessionId).browserPath
  ).then(agentServicePayloadResponse);
  if (!response.ok) {
    return [];
  }
  return response.json();
}

export async function moveChatSession(
  projectId: ProjectId,
  chatSessionId: ChatSessionId
): Promise<boolean> {
  await requestProjectRaw(
    projectsEndpoints.moveChatSession(projectId).browserPath,
    "Move chat session",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_session_id: chatSessionId }),
    }
  );
  return true;
}

export async function removeChatSessionFromProject(
  chatSessionId: ChatSessionId
): Promise<boolean> {
  await requestProjectRaw(
    projectsEndpoints.removeChatSession.browserPath,
    "Remove chat session from project",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_session_id: chatSessionId }),
    }
  );
  return true;
}
