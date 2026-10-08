import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentCard } from "@/app/app/message/messageComponents/renderers/DocumentCard";
import { fetchDocumentByFile } from "@/lib/api/domains/documents/api";
import { refreshAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import type { GeneratedFile } from "@/lib/api/domains/chat/streaming-types";

jest.mock("@/lib/api/domains/documents/api", () => ({
  fetchDocumentByFile: jest.fn(),
}));
jest.mock("@/lib/api/domains/documents/hooks", () => ({
  refreshAuthoredDocument: jest.fn(),
}));

const base: GeneratedFile = {
  type: "generated_file",
  file_id: "f2",
  filename: "Tedarikci_Onboarding_Sureci.docx",
  mime_type:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size_bytes: 24576,
  download_url: "/api/chat/file/f2?download=1",
};
const draft: GeneratedFile = {
  ...base,
  document_id: "d",
  revision_no: 2,
  revision_count: 2,
  operation: "edit",
  summary: "Hukuk incelemesi eklendi",
  stats: {
    added: 9,
    removed: 3,
    changes: [
      { kind: "paragraph", label: "Amaç", change: "modified" },
      { kind: "mermaid", label: "Süreç akışı", change: "modified" },
      { kind: "table", label: "SLA", change: "modified" },
      { kind: "paragraph", label: "Ek", change: "added" },
    ],
  },
  diagram_check: "passed",
};
const state = () => useDocumentPanelStore.getState();

beforeEach(() => {
  jest.clearAllMocks();
  useDocumentPanelStore.setState({
    ...initialDocumentPanelState,
    hostMounted: true,
  });
});

it("renders the draft card with stats and change chips", () => {
  renderWithI18n(
    <DocumentCard file={draft} isLive={false} onFallbackOpen={jest.fn()} />,
    "tr"
  );

  expect(screen.getByText("Doküman düzenlendi")).toBeInTheDocument();
  expect(screen.getByText("4 değişiklik uygulandı")).toBeInTheDocument();
  expect(screen.getByText("DOCX")).toBeInTheDocument();
  expect(screen.getByText("Taslak 2")).toBeInTheDocument();
  expect(screen.getByText("+9 −3")).toBeInTheDocument();
  expect(screen.getByText("“Amaç” güncellendi")).toBeInTheDocument();
  expect(screen.getByText("+1")).toBeInTheDocument();
});

it("opens the panel on the Changes tab for an edit", async () => {
  renderWithI18n(
    <DocumentCard file={draft} isLive={false} onFallbackOpen={jest.fn()} />,
    "tr"
  );
  fireEvent.click(screen.getByRole("button", { name: "Farkı gör" }));

  await waitFor(() =>
    expect(state()).toMatchObject({
      isOpen: true,
      documentId: "d",
      revisionNo: 2,
      tab: "changes",
    })
  );
});

it("opens draft 1 on Preview with the Aç label", async () => {
  renderWithI18n(
    <DocumentCard
      file={{ ...draft, revision_no: 1, operation: "create" }}
      isLive={false}
      onFallbackOpen={jest.fn()}
    />,
    "tr"
  );
  fireEvent.click(screen.getByRole("button", { name: "Aç" }));

  await waitFor(() =>
    expect(state()).toMatchObject({ revisionNo: 1, tab: "preview" })
  );
});

it("resolves a legacy card through by-file and falls back to read-only", async () => {
  jest.mocked(fetchDocumentByFile).mockResolvedValue(null);
  renderWithI18n(
    <DocumentCard file={base} isLive={false} onFallbackOpen={jest.fn()} />,
    "tr"
  );
  fireEvent.click(screen.getByRole("button", { name: "Aç" }));

  await waitFor(() =>
    expect(state().legacyFile).toMatchObject({ fileId: "f2" })
  );
  expect(fetchDocumentByFile).toHaveBeenCalledWith("f2");
});

it("uses the modal fallback where no panel host exists (shared chat)", async () => {
  useDocumentPanelStore.setState({ hostMounted: false });
  const onFallbackOpen = jest.fn();
  renderWithI18n(
    <DocumentCard
      file={draft}
      isLive={false}
      onFallbackOpen={onFallbackOpen}
    />,
    "tr"
  );
  fireEvent.click(screen.getByRole("button", { name: "Farkı gör" }));

  await waitFor(() => expect(onFallbackOpen).toHaveBeenCalled());
  expect(state().isOpen).toBe(false);
});

it("announces only live cards", () => {
  useDocumentPanelStore.getState().openDocument("d", 1);
  useDocumentPanelStore.getState().syncHead("d", 1);
  const { rerender } = renderWithI18n(
    <DocumentCard file={draft} isLive={false} onFallbackOpen={jest.fn()} />,
    "tr"
  );
  expect(refreshAuthoredDocument).not.toHaveBeenCalled();

  rerender(<DocumentCard file={draft} isLive onFallbackOpen={jest.fn()} />);
  expect(refreshAuthoredDocument).toHaveBeenCalledWith("d");
  expect(state()).toMatchObject({ revisionNo: 2, knownHead: 2 });
});

it("renders a chip for every change even when several share a kind, label and change", () => {
  const consoleError = jest.spyOn(console, "error").mockImplementation();
  const twin = { kind: "paragraph", label: "Önsöz", change: "added" } as const;
  renderWithI18n(
    <DocumentCard
      file={{
        ...draft,
        stats: { added: 2, removed: 0, changes: [twin, twin] },
      }}
      isLive={false}
      onFallbackOpen={jest.fn()}
    />,
    "tr"
  );

  expect(screen.getAllByText("“Önsöz” eklendi")).toHaveLength(2);
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});
