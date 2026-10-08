import { fireEvent, screen, within } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { HistoryTab } from "@/sections/document-panel/HistoryTab";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";

const restore = jest.fn();
jest.mock("@/sections/document-panel/useRevisionActions", () => ({
  useRevisionActions: () => ({ restore, restoring: false }),
}));

const rev = (n: number, over: Record<string, unknown> = {}) => ({
  revision_no: n,
  operation: n === 1 ? "create" : "edit",
  author_type: "agent",
  summary: `Özet ${n}`,
  format: "docx",
  stats: { added: n === 1 ? 0 : 9, removed: n === 1 ? 0 : 3, changes: [] },
  rendered_file_id: null,
  created_at: "2026-09-28T14:18:00Z",
  ...over,
});
const doc = {
  document_id: "d",
  head_revision_no: 3,
  revisions: [
    rev(1),
    rev(2),
    rev(3, { author_type: "user", operation: "user_edit", summary: "" }),
  ],
} as never;

beforeEach(() => {
  restore.mockReset();
  useDocumentPanelStore.setState(initialDocumentPanelState);
  useDocumentPanelStore.getState().openDocument("d", 3, "history");
});

it("lists drafts newest first with author, summary and stats", () => {
  renderWithI18n(<HistoryTab document={doc} viewed={3} />, "tr");

  const items = screen.getAllByTestId("history-item");
  expect(
    items.map((i) => within(i).getByText(/^Taslak \d$/).textContent)
  ).toEqual(["Taslak 3", "Taslak 2", "Taslak 1"]);
  expect(within(items[0]!).getByText("Güncel")).toBeInTheDocument();
  expect(within(items[0]!).getByText("Özet yok")).toBeInTheDocument();
  expect(
    within(items[0]!).getByText(/^Siz · kullanıcı düzenlemesi · /)
  ).toBeInTheDocument();
  expect(within(items[1]!).getByText("+9 −3")).toBeInTheDocument();
  expect(
    within(items[0]!).queryByRole("button", { name: "Geri yükle" })
  ).not.toBeInTheDocument();
});

it("views, compares with latest and restores", () => {
  renderWithI18n(<HistoryTab document={doc} viewed={3} />, "tr");
  const second = screen.getAllByTestId("history-item")[1]!;

  fireEvent.click(
    within(second).getByRole("button", { name: "Güncel ile karşılaştır" })
  );
  expect(useDocumentPanelStore.getState()).toMatchObject({
    compare: { left: 2, right: 3 },
    tab: "compare",
  });

  fireEvent.click(within(second).getByRole("button", { name: "Görüntüle" }));
  expect(useDocumentPanelStore.getState()).toMatchObject({
    revisionNo: 2,
    tab: "preview",
  });

  fireEvent.click(within(second).getByRole("button", { name: "Geri yükle" }));
  expect(restore).toHaveBeenCalledWith(2, 3);
});
