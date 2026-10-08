import { fireEvent, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { PreviewTab } from "@/sections/document-panel/PreviewTab";
import { useRevision } from "@/lib/api/domains/documents/hooks";

jest.mock("@/lib/api/domains/documents/hooks");
jest.mock("@/components/mermaid/MermaidDiagram", () => {
  const Stub = (p: {
    source: string;
    variant: string;
    onRequestFix?: (s: string, d: unknown) => void;
  }) => (
    <div data-testid="mermaid-stub" data-variant={p.variant}>
      {p.source}
      {p.onRequestFix && (
        <button
          type="button"
          onClick={() =>
            p.onRequestFix!(p.source, {
              kind: "parse",
              message: "bad",
              line: 2,
            })
          }
        >
          fix
        </button>
      )}
    </div>
  );
  return { __esModule: true, MermaidDiagram: Stub, default: Stub };
});

const revision = (over: Record<string, unknown>) =>
  ({
    data: {
      revision_no: 2,
      source_format: "markdown",
      content: "# Başlık",
      ...over,
    },
    isLoading: false,
    error: undefined,
  }) as never;

it("renders markdown with document-variant mermaid", () => {
  jest
    .mocked(useRevision)
    .mockReturnValue(
      revision({ content: "# Süreç\n\n```mermaid\nflowchart LR\n  A-->B\n```" })
    );
  renderWithI18n(<PreviewTab documentId="d" revisionNo={2} />);

  expect(screen.getByRole("heading", { name: "Süreç" })).toBeInTheDocument();
  expect(screen.getByTestId("mermaid-stub")).toHaveAttribute(
    "data-variant",
    "document"
  );
  expect(screen.queryByRole("button", { name: "fix" })).not.toBeInTheDocument();
});

it("forwards the fix request when a handler is given", () => {
  const onFix = jest.fn();
  jest
    .mocked(useRevision)
    .mockReturnValue(
      revision({ content: "```mermaid\nflowchart LR\n  A BROKEN B\n```" })
    );
  renderWithI18n(
    <PreviewTab documentId="d" revisionNo={2} onRequestMermaidFix={onFix} />
  );

  fireEvent.click(screen.getByRole("button", { name: "fix" }));
  expect(onFix).toHaveBeenCalledWith("flowchart LR\n  A BROKEN B", {
    kind: "parse",
    message: "bad",
    line: 2,
  });
});

it("renders a spreadsheet as tables", () => {
  jest.mocked(useRevision).mockReturnValue(
    revision({
      source_format: "sheets_json",
      content: JSON.stringify([
        {
          name: "SLA",
          rows: [
            ["Adım", "Süre"],
            ["Belge", "3"],
          ],
        },
      ]),
    })
  );
  renderWithI18n(<PreviewTab documentId="d" revisionNo={2} />);

  expect(screen.getByRole("heading", { name: "SLA" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Belge" })).toBeInTheDocument();
});

it("shows a retry on load failure", () => {
  const mutate = jest.fn();
  jest.mocked(useRevision).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: new Error("x"),
    mutate,
  } as never);
  renderWithI18n(<PreviewTab documentId="d" revisionNo={2} />);

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(mutate).toHaveBeenCalled();
});

it("keeps the paper while the revision loads", () => {
  jest.mocked(useRevision).mockReturnValue({
    data: undefined,
    isLoading: true,
    error: undefined,
    mutate: jest.fn(),
  } as never);
  renderWithI18n(<PreviewTab documentId="d" revisionNo={2} />);

  const loading = screen.getByTestId("preview-loading");
  expect(
    loading.querySelector("[data-testid='document-preview-skeleton']")
  ).not.toBeNull();
});
