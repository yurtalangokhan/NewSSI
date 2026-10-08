import { act, fireEvent, renderHook, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { OldRevisionBanner } from "@/sections/document-panel/OldRevisionBanner";
import { NewDraftNotice } from "@/sections/document-panel/NewDraftNotice";
import { useRevisionActions } from "@/sections/document-panel/useRevisionActions";
import {
  RevisionConflictError,
  restoreRevision,
} from "@/lib/api/domains/documents/api";
import { refreshAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import { toast } from "@/hooks/useToast";

jest.mock("@/lib/api/domains/documents/api", () => ({
  ...jest.requireActual("@/lib/api/domains/documents/api"),
  restoreRevision: jest.fn(),
}));
jest.mock("@/lib/api/domains/documents/hooks", () => ({
  refreshAuthoredDocument: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const created = (no: number) => ({ revision: { revision_no: no } }) as never;

beforeEach(() => {
  jest.clearAllMocks();
  useDocumentPanelStore.setState(initialDocumentPanelState);
  useDocumentPanelStore.getState().openDocument("d", 1);
});

it("shows the banner and continues from the old draft", () => {
  const onContinue = jest.fn();
  renderWithI18n(
    <OldRevisionBanner
      onContinue={onContinue}
      onGoToLatest={jest.fn()}
      busy={false}
    />,
    "tr"
  );

  expect(
    screen.getByText("Eski bir taslağı görüntülüyorsunuz.")
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Bu taslaktan devam et" })
  );
  expect(onContinue).toHaveBeenCalled();
});

it("announces a newer draft", () => {
  const onView = jest.fn();
  renderWithI18n(<NewDraftNotice revisionNo={4} onView={onView} />, "tr");
  fireEvent.click(screen.getByRole("button", { name: "Görüntüle" }));
  expect(screen.getByText("Taslak 4 hazır.")).toBeInTheDocument();
  expect(onView).toHaveBeenCalled();
});

it("restores, selects the new draft and refreshes", async () => {
  jest.mocked(restoreRevision).mockResolvedValue(created(4));
  const { result } = renderHook(() => useRevisionActions("d"));

  await act(() => result.current.restore(1, 3));

  expect(restoreRevision).toHaveBeenCalledWith("d", 1, 3);
  expect(useDocumentPanelStore.getState().revisionNo).toBe(4);
  expect(refreshAuthoredDocument).toHaveBeenCalledWith("d");
  expect(toast.success).toHaveBeenCalled();
});

it("retries once on a conflict with the reported head", async () => {
  jest
    .mocked(restoreRevision)
    .mockRejectedValueOnce(new RevisionConflictError(5))
    .mockResolvedValueOnce(created(6));
  const { result } = renderHook(() => useRevisionActions("d"));

  await act(() => result.current.restore(1, 3));

  expect(jest.mocked(restoreRevision).mock.calls).toEqual([
    ["d", 1, 3],
    ["d", 1, 5],
  ]);
  expect(useDocumentPanelStore.getState().revisionNo).toBe(6);
});
