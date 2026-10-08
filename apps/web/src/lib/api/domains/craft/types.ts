// Craft API types

export interface CreateSessionRequest {
  task: string;
  available_sources?: string[];
}

export interface CreateSessionResponse {
  session_id: string;
}

export interface Session {
  id: string;
  name?: string;
  status?: "running" | "completed" | "failed";
  created_at?: string;
}

export interface FileSystemEntry {
  name: string;
  path: string;
  is_directory: boolean;
  size: number | null;
  mime_type: string | null;
}

export interface DirectoryListing {
  path: string;
  entries: FileSystemEntry[];
}

export interface ArtifactInfo {
  artifact_type: "webapp" | "file" | "markdown" | "image";
  path: string;
  filename: string;
  mime_type?: string;
}

export interface WebappInfo {
  url?: string;
  status?: string;
}

export interface LibraryTree {
  path: string;
  entries: FileSystemEntry[];
}

export interface UsageLimits {
  limit?: number;
  used?: number;
  remaining?: number;
}

export interface UploadResponse {
  files: FileSystemEntry[];
}
