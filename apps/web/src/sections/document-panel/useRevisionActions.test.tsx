import { act, renderHook } from "@testing-library/react";
import {
  DiagramInvalidError,
  DocumentNoChangeError,
  RevisionConflictError,
  restoreRevision,
} from "@/lib/api/domains/documents/api";
import { FetchError } from "@/lib/api/http/errors";
import { toast } from "@/hooks/useToast";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import { useRevisionActions } from "@/sections/document-panel/useRevisionActions";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key} ${JSON.stringify(values)}` : key,
  }),
}));
jest.mock("@/lib/api/domains/documents/api", () => ({
  ...jest.requireActual("@/lib/api/domains/documents/api"),
  restoreRevision: jest.fn(),
}));
jest.mock("@/lib/api/domains/documents/hooks", () => ({
  refreshAuthoredDocument: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

async function restore() {
  const { result } = renderHook(() => useRevisionActions("d"));
  await act(async () => {
    await result.current.restore(1, 3);
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  useDocumentPanelStore.setState(initialDocumentPanelState);
  useDocumentPanelStore.getState().openDocument("d", 1);
});

it("selects the created draft on success", async () => {
  jest
    .mocked(restoreRevision)
    .mockResolvedValue({ revision: { revision_no: 4 } } as never);
  await restore();
  expect(useDocumentPanelStore.getState().revisionNo).toBe(4);
  expect(toast.success).toHaveBeenCalled();
});

it("retries once on the newer head after a conflict", async () => {
  jest
    .mocked(restoreRevision)
    .mockRejectedValueOnce(new RevisionConflictError(5))
    .mockResolvedValueOnce({ revision: { revision_no: 6 } } as never);
  await restore();
  expect(restoreRevision).toHaveBeenLastCalledWith("d", 1, 5);
  expect(useDocumentPanelStore.getState().revisionNo).toBe(6);
});

it("tells the user when the draft equals the current one", async () => {
  jest.mocked(restoreRevision).mockRejectedValue(new DocumentNoChangeError());
  await restore();
  expect(toast.info).toHaveBeenCalledWith("documentPanel.restoreNoChange");
  expect(toast.error).not.toHaveBeenCalled();
});

it("reports an invalid diagram with its own message", async () => {
  jest.mocked(restoreRevision).mockRejectedValue(new DiagramInvalidError([]));
  await restore();
  expect(toast.error).toHaveBeenCalledWith(
    "documentPanel.restoreDiagramInvalid"
  );
});

it("shows the server's message for other request errors", async () => {
  jest
    .mocked(restoreRevision)
    .mockRejectedValue(new FetchError("Document is locked", 423, {}));
  await restore();
  expect(toast.error).toHaveBeenCalledWith("Document is locked");
});

it("falls back to the generic message for unknown failures", async () => {
  jest.mocked(restoreRevision).mockRejectedValue(new Error("boom"));
  await restore();
  expect(toast.error).toHaveBeenCalledWith("documentPanel.restoreFailed");
});
