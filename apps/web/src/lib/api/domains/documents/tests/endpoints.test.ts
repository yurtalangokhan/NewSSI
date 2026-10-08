import { documentsEndpoints } from "@/lib/api/domains/documents/endpoints";

describe("documentsEndpoints", () => {
  it("routes the detail through the agent gateway family", () => {
    expect(documentsEndpoints.getDocument("d 1")).toEqual({
      method: "GET",
      browserPath: "/api/documents/d%201",
      backend: { service: "agent", path: "/api/v1/documents/d%201" },
    });
  });

  it("builds revision, by-file, mutation and export paths", () => {
    expect(documentsEndpoints.getRevision("d", 3).browserPath).toBe(
      "/api/documents/d/revisions/3"
    );
    expect(documentsEndpoints.getByFile("f/1").browserPath).toBe(
      "/api/documents/by-file/f%2F1"
    );
    expect(documentsEndpoints.createRevision("d")).toMatchObject({
      method: "POST",
      browserPath: "/api/documents/d/revisions",
    });
    expect(documentsEndpoints.restoreRevision("d", 2)).toMatchObject({
      method: "POST",
      browserPath: "/api/documents/d/revisions/2/restore",
    });
    expect(documentsEndpoints.exportRevision("d", 2, "docx").browserPath).toBe(
      "/api/documents/d/revisions/2/export?format=docx"
    );
  });
});
