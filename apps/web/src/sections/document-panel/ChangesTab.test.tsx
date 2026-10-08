import { fireEvent, screen, within } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { ChangesTab } from "@/sections/document-panel/ChangesTab";
import { useRevisionPair } from "@/lib/api/domains/documents/hooks";
import { MAX_DIFF_CHARS } from "@/lib/documents/diff/blockDiff";

jest.mock("@/lib/api/domains/documents/hooks");
jest.mock("@/sections/document-panel/LazyCodeEditor", () => ({
  LazyCodeEditor: (p: { value: string; mergeOriginal?: string }) => (
    <pre data-testid="source-diff" data-original={p.mergeOriginal}>
      {p.value}
    </pre>
  ),
}));
jest.mock("@/components/mermaid/MermaidDiagram", () => {
  const Stub = (p: { source: string }) => (
    <div data-testid="mermaid-stub">{p.source}</div>
  );
  return { __esModule: true, MermaidDiagram: Stub, default: Stub };
});

const doc = { document_id: "d", head_revision_no: 3, revisions: [] } as never;
const side = (content: string) => ({
  data: { content, source_format: "markdown" },
});

// The hook always runs (rules of hooks), so every test needs a shape.
beforeEach(() => {
  jest.mocked(useRevisionPair).mockReturnValue({
    left: {},
    right: {},
    isLoading: false,
    error: undefined,
  } as never);
});

function pair(before: string, after: string) {
  jest.mocked(useRevisionPair).mockReturnValue({
    left: side(before),
    right: side(after),
    isLoading: false,
    error: undefined,
  } as never);
}

const BEFORE =
  "# A\n\nBir\n\nİki\n\nÜç\n\nAmaç eski.\n\n| Adım | Süre |\n|---|---|\n| Belge | 3 |\n\n```mermaid\nflowchart LR\n  A-->B\n```";
const AFTER =
  "# A\n\nBir\n\nİki\n\nÜç\n\nAmaç yeni.\n\n| Adım | Süre |\n|---|---|\n| Belge | 2 |\n| Hukuk | 3 |\n\n```mermaid\nflowchart LR\n  A-->C\n```\n\n## Yeni";

it("shows the first-draft empty state", () => {
  renderWithI18n(<ChangesTab document={doc} revisionNo={1} />, "tr");
  expect(screen.getByText("Bu ilk taslak")).toBeInTheDocument();
});

it("renders folded unchanged runs, inline changes, table cells and diagram pairs", () => {
  pair(BEFORE, AFTER);
  renderWithI18n(<ChangesTab document={doc} revisionNo={3} />, "tr");

  expect(screen.getByText("Taslak 2 → Taslak 3")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "4 blok değişmedi" })
  ).toBeInTheDocument();
  // jsdiff keeps the trailing "." as its own unchanged token.
  expect(screen.getByText("eski", { selector: "del" })).toBeInTheDocument();
  expect(screen.getByText("yeni", { selector: "ins" })).toBeInTheDocument();
  expect(
    screen.getByText("Tablo değişti · 1 hücre, +1 −0 satır")
  ).toBeInTheDocument();
  expect(
    screen.getAllByTestId("mermaid-stub").map((n) => n.textContent)
  ).toEqual(["flowchart LR\n  A-->B", "flowchart LR\n  A-->C"]);
  expect(
    screen.getAllByTestId("diff-block").map((b) => b.dataset.status)
  ).toEqual(["modified", "modified", "modified", "added"]);

  fireEvent.click(screen.getByRole("button", { name: "4 blok değişmedi" }));
  expect(screen.getByText("Bir")).toBeInTheDocument();
});

it("switches to the source diff", () => {
  pair("a", "b");
  renderWithI18n(<ChangesTab document={doc} revisionNo={2} />, "tr");

  fireEvent.click(screen.getByRole("button", { name: "Kaynak" }));
  expect(screen.getByTestId("source-diff")).toHaveAttribute(
    "data-original",
    "a"
  );
});

it("falls back to the source diff for huge documents", () => {
  pair("x".repeat(MAX_DIFF_CHARS + 1), "y");
  renderWithI18n(<ChangesTab document={doc} revisionNo={2} />, "tr");

  expect(
    screen.getByText(
      "Doküman işlenmiş fark için çok büyük; kaynak farkı gösteriliyor."
    )
  ).toBeInTheDocument();
  expect(screen.getByTestId("source-diff")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "İşlenmiş" })
  ).not.toBeInTheDocument();
});

it("shows a retryable error instead of a skeleton when a revision fails to load", () => {
  const retry = jest.fn();
  jest.mocked(useRevisionPair).mockReturnValue({
    left: {},
    right: {},
    isLoading: false,
    error: new Error("boom"),
    retry,
  } as never);
  renderWithI18n(<ChangesTab document={doc} revisionNo={3} />, "tr");

  expect(screen.getByText("Doküman yüklenemedi.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

it("keeps a modified code block whose body contains a fence in one block", () => {
  const wrap = (body: string) => `\`\`\`\`md\n${body}\n\`\`\`\``;
  pair(
    wrap("Kullanım:\n```js\nold()\n```"),
    wrap("Kullanım:\n```js\nnew()\n```")
  );
  renderWithI18n(<ChangesTab document={doc} revisionNo={3} />, "tr");

  const block = screen.getByTestId("diff-block");
  expect(block.textContent).toContain("old()");
  expect(block.textContent).toContain("new()");
  // The inner fence stays literal code instead of closing the block early.
  expect(within(block).getAllByTestId("code-block")).toHaveLength(2);
});
