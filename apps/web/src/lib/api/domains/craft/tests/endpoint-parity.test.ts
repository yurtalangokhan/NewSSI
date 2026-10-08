import { craftEndpoints } from "@/lib/api/domains/craft/endpoints";

describe("craft endpoint parity", () => {
  it("preserves raw session IDs and pre-encoded artifact paths", () => {
    const sessionId = "session/ space/ç";
    const encodedPath = "dir/file%20name-%C3%A7.txt";

    expect(craftEndpoints.craftSessions.browserPath).toBe(
      "/api/build/sessions"
    );
    expect(craftEndpoints.craftSessionRequest(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}`
    );
    expect(craftEndpoints.craftSessionGenerateName(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/generate-name`
    );
    expect(craftEndpoints.craftSessionSuggestions(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/generate-suggestions`
    );
    expect(craftEndpoints.craftSessionName(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/name`
    );
    expect(craftEndpoints.craftSessionSharing(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/public`
    );
    expect(
      craftEndpoints.craftSessionPreProvisionedCheck(sessionId).browserPath
    ).toBe(`/api/build/sessions/${sessionId}/pre-provisioned-check`);
    expect(craftEndpoints.craftSessionMessages(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/messages`
    );
    expect(craftEndpoints.craftSessionSendMessage(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/send-message`
    );
    expect(craftEndpoints.craftSessionArtifacts(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/artifacts`
    );
    expect(craftEndpoints.craftSessionWebappInfo(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/webapp-info`
    );
    expect(craftEndpoints.craftSessionFilesRequest(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/files`
    );
    expect(
      craftEndpoints.craftArtifactDownload(sessionId, encodedPath).browserPath
    ).toBe(`/api/build/sessions/${sessionId}/artifacts/${encodedPath}`);
    expect(
      craftEndpoints.craftDirectoryDownload(sessionId, encodedPath).browserPath
    ).toBe(
      `/api/build/sessions/${sessionId}/download-directory/${encodedPath}`
    );
    expect(craftEndpoints.craftSessionUpload(sessionId).browserPath).toBe(
      `/api/build/sessions/${sessionId}/upload`
    );
    expect(
      craftEndpoints.craftSessionDocxExport(sessionId, encodedPath).browserPath
    ).toBe(`/api/build/sessions/${sessionId}/export-docx/${encodedPath}`);
    expect(
      craftEndpoints.craftSessionPptxPreview(sessionId, encodedPath).browserPath
    ).toBe(`/api/build/sessions/${sessionId}/pptx-preview/${encodedPath}`);
  });

  it("preserves library encoding and query order", () => {
    expect(craftEndpoints.craftUsageLimits.browserPath).toBe(
      "/api/build/limit"
    );
    expect(craftEndpoints.userLibraryTree.browserPath).toBe(
      "/api/build/user-library/tree"
    );
    expect(craftEndpoints.userLibraryUpload.browserPath).toBe(
      "/api/build/user-library/upload"
    );
    expect(craftEndpoints.userLibraryUploadZip.browserPath).toBe(
      "/api/build/user-library/upload-zip"
    );
    expect(craftEndpoints.userLibraryDirectories.browserPath).toBe(
      "/api/build/user-library/directories"
    );
    expect(
      craftEndpoints.userLibraryFileSync("slash/ space/ç", true).browserPath
    ).toBe(
      "/api/build/user-library/files/slash%2F%20space%2F%C3%A7/toggle?enabled=true"
    );
    expect(craftEndpoints.userLibraryFile("slash/ space/ç").browserPath).toBe(
      "/api/build/user-library/files/slash%2F%20space%2F%C3%A7"
    );
  });
});
