// Craft/Build API endpoint paths

export type SessionId = string;

// Preserve browser cache/download keys verbatim; request builders may encode separately.

export const craftEndpoints = {
  craftSessions: { browserPath: "/api/build/sessions" },
  craftSession: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${encodeURIComponent(sessionId)}`,
    };
  },
  craftSessionArtifact: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${encodeURIComponent(
        sessionId
      )}/artifacts/${encodedPath}`,
    };
  },
  craftSessionFiles: (
    sessionId: string,
    path?: string
  ): { browserPath: string } => {
    const base = `/api/build/sessions/${encodeURIComponent(sessionId)}/files`;
    return {
      browserPath:
        path !== undefined ? `${base}?path=${encodeURIComponent(path)}` : base,
    };
  },
  craftRestore: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${encodeURIComponent(
        sessionId
      )}/restore`,
    };
  },
  fetchCraftFilePreview: (
    sessionId: string,
    filePath: string
  ): { browserPath: string } => {
    return {
      browserPath: craftEndpoints.craftSessionArtifact(
        sessionId,
        encodeURIComponent(filePath)
      ).browserPath,
    };
  },
  apiBase: { browserPath: "/api/build" },
  craftUsageLimits: { browserPath: "/api/build/limit" },
  craftSessionRequest: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${craftEndpoints.craftSessions.browserPath}/${sessionId}`,
    };
  },
  craftSessionGenerateName: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/generate-name`,
    };
  },
  craftSessionSuggestions: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/generate-suggestions`,
    };
  },
  craftSessionName: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/name`,
    };
  },
  craftSessionSharing: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/public`,
    };
  },
  craftSessionPreProvisionedCheck: (
    sessionId: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/pre-provisioned-check`,
    };
  },
  craftSessionMessages: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/messages`,
    };
  },
  craftSessionSendMessage: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/send-message`,
    };
  },
  craftSessionArtifacts: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/artifacts`,
    };
  },
  craftSessionWebappInfo: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/webapp-info`,
    };
  },
  craftSessionFilesRequest: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/files`,
    };
  },
  craftArtifactDownload: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionArtifacts(sessionId).browserPath
      }/${encodedPath}`,
    };
  },
  craftDirectoryDownload: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/download-directory/${encodedPath}`,
    };
  },
  craftSessionUpload: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/upload`,
    };
  },
  craftSessionFile: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionFilesRequest(sessionId).browserPath
      }/${encodedPath}`,
    };
  },
  craftSessionDocxExport: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/export-docx/${encodedPath}`,
    };
  },
  craftSessionPptxPreview: (
    sessionId: string,
    encodedPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.craftSessionRequest(sessionId).browserPath
      }/pptx-preview/${encodedPath}`,
    };
  },
  userLibrary: { browserPath: "/api/build/user-library" },
  userLibraryTree: { browserPath: "/api/build/user-library/tree" },
  userLibraryUpload: { browserPath: "/api/build/user-library/upload" },
  userLibraryUploadZip: { browserPath: "/api/build/user-library/upload-zip" },
  userLibraryDirectories: {
    browserPath: "/api/build/user-library/directories",
  },
  userLibraryFileSync: (
    documentId: string,
    enabled: boolean
  ): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.userLibrary.browserPath
      }/files/${encodeURIComponent(documentId)}/toggle?enabled=${enabled}`,
    };
  },
  userLibraryFile: (documentId: string): { browserPath: string } => {
    return {
      browserPath: `${
        craftEndpoints.userLibrary.browserPath
      }/files/${encodeURIComponent(documentId)}`,
    };
  },
  craftWebappInfoKey: (sessionId: string): { browserPath: string } => {
    return { browserPath: `/api/build/sessions/${sessionId}/webapp-info` };
  },
  craftArtifactCacheKey: (
    sessionId: string,
    artifactPath: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${sessionId}/artifacts/${artifactPath}`,
    };
  },
  craftArtifactsKey: (sessionId: string): { browserPath: string } => {
    return { browserPath: `/api/build/sessions/${sessionId}/artifacts` };
  },
  craftOutputFilesKey: (sessionId: string): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${sessionId}/files?path=outputs`,
    };
  },
  craftWebappDownload: (sessionId: string): { browserPath: string } => {
    return { browserPath: `/api/build/sessions/${sessionId}/webapp/download` };
  },
  craftFilesQueryPrefix: (sessionId: string): { browserPath: string } => {
    return { browserPath: `/api/build/sessions/${sessionId}/files?path=` };
  },
  craftPptxPreviewCacheKey: (
    sessionId: string,
    filePath: string
  ): { browserPath: string } => {
    return {
      browserPath: `/api/build/sessions/${sessionId}/pptx-preview/${filePath}`,
    };
  },
  userLibraryTreeKey: { browserPath: "/api/build/user-library/tree" },
} as const;
