import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentPanel } from "@/sections/document-panel/DocumentPanel";
import {
  useAuthoredDocument,
  useRevision,
} from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import { setWhitePageMode } from "@/sections/document-panel/useWhitePage";

jest.mock("@/lib/api/domains/documents/hooks");
jest.mock("@/sections/document-panel/PreviewTab", () => ({
  PreviewTab: ({ revisionNo }: { revisionNo: number }) => (
    <div data-testid="preview-tab">rev {revisionNo}</div>
  ),
}));
jest.mock("@/sections/document-panel/LegacyFileBody", () => ({
  LegacyFileBody: () => <div data-testid="legacy-file-body" />,
}));
let exportMenuRenders = 0;
jest.mock("@/sections/document-panel/ExportMenu", () => ({
  ExportMenu: () => {
    exportMenuRenders += 1;
    return <div data-testid="export-menu" />;
  },
}));
jest.mock("@/sections/document-panel/EditTab", () => ({
  EditTab: () => <div data-testid="edit-tab" />,
}));
const restore = jest.fn();
jest.mock("@/sections/document-panel/useRevisionActions", () => ({
  useRevisionActions: () => ({ restore, restoring: false }),
}));

const summary = (n: number) => ({
  revision_no: n,
  operation: "edit",
  author_type: "agent",
  summary: "",
  format: "docx",
  stats: { added: 0, removed: 0, changes: [] },
  rendered_file_id: null,
  created_at: "2026-09-28T14:00:00Z",
});

function mockDocument(head: number) {
  jest.mocked(useAuthoredDocument).mockReturnValue({
    data: {
      document_id: "d",
      kind: "document",
      title: "T",
      filename: "T.docx",
      format: "docx",
      head_revision_no: head,
      thread_id: "t",
      updated_at: "",
      revisions: Array.from({ length: head }, (_, i) => summary(i + 1)),
    },
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  } as never);
}

beforeEach(() => {
  jest.clearAllMocks();
  exportMenuRenders = 0;
  useDocumentPanelStore.setState(initialDocumentPanelState);
  setWhitePageMode("off");
  jest.mocked(useRevision).mockReturnValue({
    data: { content: "# T", source_format: "markdown" },
    isLoading: false,
  } as never);
});

it("follows the head and shows no old-draft banner there", () => {
  mockDocument(3);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  expect(screen.getByTestId("preview-tab")).toHaveTextContent("rev 3");
  expect(
    screen.queryByText("Eski bir taslağı görüntülüyorsunuz.")
  ).not.toBeInTheDocument();
});

it("shows the old-draft banner and restores from it", () => {
  mockDocument(3);
  act(() => useDocumentPanelStore.getState().openDocument("d", 1));
  renderWithI18n(<DocumentPanel />, "tr");

  fireEvent.click(
    screen.getByRole("button", { name: "Bu taslaktan devam et" })
  );
  expect(restore).toHaveBeenCalledWith(1, 3);
});

it("shows a new-draft notice when a newer head arrives mid-view", () => {
  mockDocument(3);
  act(() => useDocumentPanelStore.getState().openDocument("d", 2));
  const view = renderWithI18n(<DocumentPanel />, "tr");

  mockDocument(4);
  act(() => useDocumentPanelStore.getState().revisionPublished("d", 4));
  view.rerender(<DocumentPanel />);

  fireEvent.click(screen.getByRole("button", { name: "Görüntüle" }));
  expect(screen.getByTestId("preview-tab")).toHaveTextContent("rev 4");
});

it("opens the editor on the viewed draft", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  fireEvent.click(screen.getByRole("button", { name: "Düzenle" }));
  expect(useDocumentPanelStore.getState().edit).toMatchObject({
    baseRevisionNo: 2,
    text: "# T",
  });
});

it("renders legacy files read-only", () => {
  act(() =>
    useDocumentPanelStore.getState().openLegacyFile({
      fileId: "f",
      filename: "eski.pdf",
      mimeType: "application/pdf",
    })
  );
  renderWithI18n(<DocumentPanel />, "tr");

  expect(screen.getByTestId("legacy-file-body")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Düzenle" })
  ).not.toBeInTheDocument();
  expect(screen.queryByTestId("revision-switcher")).not.toBeInTheDocument();
});

it("does not re-render the header and toolbar on every keystroke", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");
  fireEvent.click(screen.getByRole("button", { name: "Düzenle" }));
  expect(screen.getByTestId("edit-tab")).toBeInTheDocument();

  const before = exportMenuRenders;
  act(() => {
    useDocumentPanelStore.getState().updateDraft("# a");
    useDocumentPanelStore.getState().updateDraft("# ab");
    useDocumentPanelStore.getState().updateDraft("# abc");
  });

  expect(exportMenuRenders).toBe(before);
});

it("never labels the header with another draft while the new head is still loading", () => {
  mockDocument(3);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  const view = renderWithI18n(<DocumentPanel />, "tr");
  expect(screen.getByText(/Taslak 3 ·/)).toBeInTheDocument();

  // The publish announcement arrives before the refetched revision list.
  act(() => useDocumentPanelStore.getState().revisionPublished("d", 4));
  view.rerender(<DocumentPanel />);

  expect(screen.queryByText(/Taslak 3 ·/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Taslak 4 ·/)).not.toBeInTheDocument();
  expect(screen.queryByTestId("document-panel-header")).not.toBeInTheDocument();
});

it("renders the panel tabs as the connector dialog's underline bar", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  const tablist = screen.getByRole("tablist");
  expect(tablist).toHaveClass("border-b", "border-border-01");
  expect(tablist).not.toHaveClass("bg-background-tint-03", "pb-[5px]");

  // The active tab is the one that paints the 2px primary underline.
  expect(screen.getByRole("tab", { name: "Önizleme" })).toHaveClass(
    "data-[state=active]:border-blue-500",
    "data-[state=active]:text-text-05"
  );
  expect(screen.getByRole("tab", { name: "Değişiklikler" })).toHaveClass(
    "border-b-2",
    "border-transparent"
  );
  expect(screen.getAllByRole("tab")).toHaveLength(4);
});

it("groups the white-page toggle, export and the primary edit action", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  const actions = screen.getByTestId("document-panel-header-actions");
  // One right-aligned group: the view toggle, export, then the edit button.
  expect(actions.firstElementChild).toBe(
    screen.getByRole("button", { name: /Beyaz sayfa/ })
  );
  expect(within(actions).getByTestId("export-menu")).toBeInTheDocument();
  expect(
    within(actions).getByRole("button", { name: "Düzenle" })
  ).toHaveAttribute("data-interactive-base-prominence", "primary");
});

it("cycles the white page off → text area → whole area and remembers it", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  const toggle = () => screen.getByRole("button", { name: /Beyaz sayfa/ });
  expect(toggle()).toHaveAttribute("aria-pressed", "false");

  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute("aria-pressed", "true");
  expect(toggle()).toHaveAttribute("data-interactive-base-prominence", "light");
  expect(window.localStorage.getItem("atlas.documentPanel.whitePage")).toBe(
    "paper"
  );

  // Second press: the reading area around the sheet goes light too.
  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute("data-interactive-base-prominence", "heavy");
  expect(window.localStorage.getItem("atlas.documentPanel.whitePage")).toBe(
    "page"
  );

  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute("aria-pressed", "false");
  expect(window.localStorage.getItem("atlas.documentPanel.whitePage")).toBe(
    "off"
  );
});

it("fills the panel with a skeleton while the document loads", () => {
  jest.mocked(useAuthoredDocument).mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: true,
    mutate: jest.fn(),
  } as never);
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  renderWithI18n(<DocumentPanel />, "tr");

  expect(screen.getByTestId("document-panel")).toBeInTheDocument();
  expect(screen.getByTestId("document-panel-skeleton")).toBeInTheDocument();
  expect(screen.getByTestId("document-preview-skeleton")).toBeInTheDocument();
});

it("paints the reading viewport as the page only in the whole-area mode", () => {
  mockDocument(2);
  act(() => useDocumentPanelStore.getState().openDocument("d"));

  const dark = renderWithI18n(<DocumentPanel />, "tr");
  expect(dark.container.querySelector(".theme-light")).toBeNull();
  dark.unmount();

  // `paper` keeps the app surface around the sheet (the mocked PreviewTab draws
  // no sheet here), so the viewport stays dark.
  act(() => setWhitePageMode("paper"));
  const sheetOnly = renderWithI18n(<DocumentPanel />, "tr");
  expect(sheetOnly.container.querySelector(".theme-light")).toBeNull();
  sheetOnly.unmount();

  act(() => setWhitePageMode("page"));
  const wholeArea = renderWithI18n(<DocumentPanel />, "tr");

  // The viewport itself carries the sheet colour, so scrolled content can never
  // sit on a second surface.
  const surface = wholeArea.container.querySelector(".theme-light");
  expect(surface).not.toBeNull();
  expect(surface).toHaveClass("bg-background-tint-00");
});
