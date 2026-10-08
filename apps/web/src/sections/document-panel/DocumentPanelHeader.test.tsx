import { fireEvent, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentPanelHeader } from "@/sections/document-panel/DocumentPanelHeader";
import { RevisionSwitcher } from "@/sections/document-panel/RevisionSwitcher";
import type {
  DocumentDetail,
  RevisionSummary,
} from "@/lib/api/domains/documents/types";

const rev = (
  n: number,
  over: Partial<RevisionSummary> = {}
): RevisionSummary => ({
  revision_no: n,
  operation: n === 1 ? "create" : "edit",
  author_type: "agent",
  summary: `s${n}`,
  format: "docx",
  stats: { added: 1, removed: 0, changes: [] },
  rendered_file_id: `f${n}`,
  created_at: "2026-09-28T14:32:00Z",
  ...over,
});

const doc: DocumentDetail = {
  document_id: "d",
  kind: "document",
  title: "Tedarikçi Onboarding",
  filename: "Tedarikci_Onboarding_Sureci.docx",
  format: "docx",
  head_revision_no: 3,
  thread_id: "t",
  updated_at: "2026-09-28T14:32:00Z",
  revisions: [rev(1), rev(2), rev(3)],
};

describe("RevisionSwitcher", () => {
  it("selects drafts by pill and by prev/next", () => {
    const onSelect = jest.fn();
    renderWithI18n(
      <RevisionSwitcher
        revisions={doc.revisions}
        selected={2}
        onSelect={onSelect}
      />,
      "tr"
    );

    expect(screen.getByRole("button", { name: "Taslak 2" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    fireEvent.click(screen.getByRole("button", { name: "Taslak 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Önceki taslak" }));
    expect(onSelect.mock.calls).toEqual([[3], [1]]);
  });

  it("disables prev on the first draft and next on the head", () => {
    renderWithI18n(
      <RevisionSwitcher
        revisions={[rev(1)]}
        selected={1}
        onSelect={jest.fn()}
      />,
      "tr"
    );
    expect(
      screen.getByRole("button", { name: "Önceki taslak" })
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Sonraki taslak" })
    ).toBeDisabled();
  });
});

describe("DocumentPanelHeader", () => {
  it("shows filename and meta and wires edit and close", () => {
    const onEdit = jest.fn();
    const onClose = jest.fn();
    renderWithI18n(
      <DocumentPanelHeader
        document={doc}
        revision={rev(3)}
        onEdit={onEdit}
        onClose={onClose}
        maximized={false}
        canEdit
      />,
      "tr"
    );

    expect(
      screen.getByText("Tedarikci_Onboarding_Sureci.docx")
    ).toBeInTheDocument();
    expect(
      screen.getByText(/^Taslak 3 · Ajan · .*\d{2}[:.]\d{2}$/)
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Doküman panelini kapat" })
    );
    expect(onEdit).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
