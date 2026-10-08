import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentProgressCard } from "@/app/app/message/messageComponents/renderers/DocumentProgressCard";
import type { GenerationState } from "@/app/app/message/messageComponents/renderers/documentGenerationState";
import { useAuthoredDocument } from "@/lib/api/domains/documents/hooks";

jest.mock("@/lib/api/domains/documents/hooks", () => ({
  useAuthoredDocument: jest.fn(),
}));

const state = (over: Partial<GenerationState>): GenerationState => ({
  started: true,
  phase: "writing",
  operation: null,
  documentId: null,
  filename: "rapor.pdf",
  format: "pdf",
  chars: 0,
  applied: null,
  total: null,
  changes: [],
  end: null,
  ...over,
});

beforeEach(() =>
  jest.mocked(useAuthoredDocument).mockReturnValue({ data: undefined } as never)
);

it("keeps the create experience (writing with characters)", () => {
  renderWithI18n(<DocumentProgressCard state={state({ chars: 1200 })} />);
  expect(
    screen.getByTestId("document-generation-skeleton")
  ).toBeInTheDocument();
  expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
  expect(
    screen.getByText("Writing document... (1,200 characters)")
  ).toBeInTheDocument();
});

it("shows applying n of m with step labels for an edit", () => {
  jest
    .mocked(useAuthoredDocument)
    .mockReturnValue({ data: { head_revision_no: 3 } } as never);
  renderWithI18n(
    <DocumentProgressCard
      state={state({
        operation: "edit",
        documentId: "d",
        phase: "applying",
        applied: 1,
        total: 2,
        filename: "Tedarikci.docx",
        format: "docx",
        changes: [{ kind: "paragraph", label: "Amaç", change: "modified" }],
      })}
    />,
    "tr"
  );

  expect(screen.getByText("Taslak 4 hazırlanıyor")).toBeInTheDocument();
  expect(screen.getByText("Tedarikci.docx")).toBeInTheDocument();
  expect(screen.getByText("“Amaç” güncellendi")).toBeInTheDocument();
  expect(
    screen.getByText("Değişiklikler uygulanıyor · 1/2")
  ).toBeInTheDocument();
});

it("shows validating and rebuilding phases for an edit", () => {
  const { rerender } = renderWithI18n(
    <DocumentProgressCard
      state={state({ operation: "edit", phase: "validating", format: "docx" })}
    />,
    "tr"
  );
  expect(screen.getByText("Diyagramlar doğrulanıyor")).toBeInTheDocument();
  expect(screen.getByText("Doküman hazırlanıyor")).toBeInTheDocument();

  rerender(
    <DocumentProgressCard
      state={state({ operation: "edit", phase: "rendering", format: "docx" })}
    />
  );
  expect(screen.getByText("DOCX yeniden oluşturuluyor…")).toBeInTheDocument();
});

it("renders every change when several blocks share a kind, label and change", () => {
  const consoleError = jest.spyOn(console, "error").mockImplementation();
  const change = {
    kind: "paragraph",
    label: "Önsöz",
    change: "added",
  } as const;
  renderWithI18n(
    <DocumentProgressCard
      state={state({
        operation: "edit",
        documentId: "d",
        phase: "applying",
        changes: [change, change],
      })}
    />,
    "tr"
  );

  expect(screen.getAllByText("“Önsöz” eklendi")).toHaveLength(2);
  expect(consoleError).not.toHaveBeenCalled();
  consoleError.mockRestore();
});
