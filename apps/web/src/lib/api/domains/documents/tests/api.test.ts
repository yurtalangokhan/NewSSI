import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import {
  DiagramInvalidError,
  DocumentNoChangeError,
  RevisionConflictError,
  exportRevision,
  fetchDocumentByFile,
  fetchRevision,
  restoreRevision,
  saveUserRevision,
} from "@/lib/api/domains/documents/api";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, details: Record<string, unknown>) {
  return { error: { code, message: code, details } };
}

describe("documents api", () => {
  beforeEach(() => jest.mocked(apiRequest).mockReset());

  it("fetches a revision", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(json(200, { revision_no: 2, content: "# A" }));

    await expect(fetchRevision("d", 2)).resolves.toMatchObject({
      revision_no: 2,
    });
    expect(apiRequest).toHaveBeenCalledWith("/api/documents/d/revisions/2");
  });

  it("maps a by-file 404 to null (legacy file)", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(json(404, envelope("document.not_found", {})));

    await expect(fetchDocumentByFile("f1")).resolves.toBeNull();
  });

  it("posts a user edit with the base revision", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(json(201, { revision: { revision_no: 4 } }));

    await saveUserRevision("d", { baseRevisionNo: 3, content: "# B" });

    const [path, init] = jest.mocked(apiRequest).mock.calls[0]!;
    expect(path).toBe("/api/documents/d/revisions");
    expect(init).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(init!.body))).toEqual({
      base_revision_no: 3,
      content: "# B",
      summary: "",
    });
  });

  it("raises RevisionConflictError with the head on 409", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(
        json(
          409,
          envelope("document.revision_conflict", { head_revision_no: 5 })
        )
      );

    const error = await saveUserRevision("d", {
      baseRevisionNo: 3,
      content: "x",
    }).catch((e) => e);
    expect(error).toBeInstanceOf(RevisionConflictError);
    expect(error.headRevisionNo).toBe(5);
  });

  it("raises DiagramInvalidError with document lines on 422", async () => {
    const diagnostics = [
      { block_index: 0, document_line: 12, line: 3, message: "Parse error" },
    ];
    jest
      .mocked(apiRequest)
      .mockResolvedValue(
        json(422, envelope("document.diagram_invalid", { diagnostics }))
      );

    const error = await saveUserRevision("d", {
      baseRevisionNo: 3,
      content: "x",
    }).catch((e) => e);
    expect(error).toBeInstanceOf(DiagramInvalidError);
    expect(error.diagnostics).toEqual(diagnostics);
  });

  it("raises DocumentNoChangeError when nothing changed", async () => {
    jest
      .mocked(apiRequest)
      .mockResolvedValue(json(422, envelope("document.no_change", {})));

    await expect(
      saveUserRevision("d", { baseRevisionNo: 3, content: "x" })
    ).rejects.toBeInstanceOf(DocumentNoChangeError);
  });

  it("restores with the base revision and keeps other errors as FetchError", async () => {
    jest.mocked(apiRequest).mockResolvedValue(json(500, { detail: "boom" }));

    await expect(restoreRevision("d", 1, 3)).rejects.toBeInstanceOf(FetchError);
    const [path, init] = jest.mocked(apiRequest).mock.calls[0]!;
    expect(path).toBe("/api/documents/d/revisions/1/restore");
    expect(JSON.parse(String(init!.body))).toEqual({ base_revision_no: 3 });
  });

  describe("exportRevision", () => {
    const file = (headers: Record<string, string>) =>
      new Response("BODY", { status: 200, headers });

    it("returns the blob and the server's filename through apiRequest", async () => {
      jest.mocked(apiRequest).mockResolvedValue(
        file({
          "Content-Disposition": 'attachment; filename="Plan-d3.docx"',
        })
      );

      const result = await exportRevision("d", 3, "docx");

      expect(apiRequest).toHaveBeenCalledWith(
        "/api/documents/d/revisions/3/export?format=docx"
      );
      expect(result.filename).toBe("Plan-d3.docx");
      expect(await result.blob.text()).toBe("BODY");
    });

    it("prefers the RFC 5987 filename for non-ASCII names", async () => {
      jest.mocked(apiRequest).mockResolvedValue(
        file({
          "Content-Disposition":
            "attachment; filename=\"plan.docx\"; filename*=UTF-8''Y%C3%B6netim%20Plan%C4%B1.docx",
        })
      );

      const result = await exportRevision("d", 1, "docx");
      expect(result.filename).toBe("Yönetim Planı.docx");
    });

    it("falls back to a generated name without Content-Disposition", async () => {
      jest.mocked(apiRequest).mockResolvedValue(file({}));

      const result = await exportRevision("d", 2, "pdf");
      expect(result.filename).toBe("d-draft-2.pdf");
    });

    it("throws the localized FetchError for a domain rejection", async () => {
      jest
        .mocked(apiRequest)
        .mockResolvedValue(
          json(422, envelope("document.format_change_unsupported", {}))
        );

      await expect(exportRevision("d", 2, "pdf")).rejects.toMatchObject({
        status: 422,
        code: "document.format_change_unsupported",
      });
    });
  });
});
