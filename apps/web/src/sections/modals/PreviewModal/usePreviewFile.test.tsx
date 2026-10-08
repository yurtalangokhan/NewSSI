import { renderHook, waitFor } from "@testing-library/react";
import { usePreviewFile } from "@/sections/modals/PreviewModal/usePreviewFile";
import { fetchChatFile } from "@/lib/api/domains/chat/api";

jest.mock("@/lib/api/domains/chat/api", () => ({ fetchChatFile: jest.fn() }));
jest.mock("react-i18next", () => ({
  ...jest.requireActual("react-i18next"),
  useTranslation: () => ({ t: (k: string) => k }),
}));

beforeAll(() => {
  Object.assign(window.URL, {
    createObjectURL: jest.fn(() => "blob:x"),
    revokeObjectURL: jest.fn(),
  });
});

/**
 * jsdom's Blob has no `text()`, so the fetch double answers with the minimal
 * shape the hook consumes: headers plus a blob that can be read back.
 */
function textFileResponse(contentType: string, body: string): Response {
  return {
    headers: new Headers({ "Content-Type": contentType }),
    blob: async () => ({ text: async () => body }),
  } as unknown as Response;
}

it("loads the file, resolves the variant and reads text content", async () => {
  jest
    .mocked(fetchChatFile)
    .mockResolvedValue(textFileResponse("text/csv", "a,b\n1,2"));

  const { result } = renderHook(() =>
    usePreviewFile({ document_id: "f1", semantic_identifier: "t.csv" })
  );

  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(fetchChatFile).toHaveBeenCalledWith("f1");
  expect(result.current.loadError).toBeNull();
  expect(result.current.ctx).toMatchObject({
    fileName: "t.csv",
    fileContent: "a,b\n1,2",
    lineCount: 2,
  });
});

it("reports a load error", async () => {
  jest.mocked(fetchChatFile).mockRejectedValue(new Error("x"));
  const { result } = renderHook(() =>
    usePreviewFile({ document_id: "f2", semantic_identifier: "a.pdf" })
  );
  await waitFor(() =>
    expect(result.current.loadError).toBe("filePreview.failedToLoadDocument")
  );
});
