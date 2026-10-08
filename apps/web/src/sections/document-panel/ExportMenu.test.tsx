import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { ExportMenu } from "@/sections/document-panel/ExportMenu";
import { exportRevision } from "@/lib/api/domains/documents/api";
import { FetchError } from "@/lib/api/http/errors";
import { toast } from "@/hooks/useToast";

jest.mock("@/lib/api/domains/documents/api", () => ({
  exportRevision: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

const createObjectURL = jest.fn(() => "blob:export");
const revokeObjectURL = jest.fn();
let clicked: { download: string; href: string }[] = [];

beforeEach(() => {
  jest.clearAllMocks();
  clicked = [];
  Object.assign(URL, { createObjectURL, revokeObjectURL });
  jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement
  ) {
    clicked.push({ download: this.download, href: this.href });
  });
});

function open() {
  renderWithI18n(
    <ExportMenu
      documentId="d"
      revisionNo={3}
      kind="document"
      sourceFormat="markdown"
    />,
    "tr"
  );
  fireEvent.click(screen.getByRole("button", { name: /Dışa aktar/ }));
}

const settled = () =>
  waitFor(() =>
    expect(screen.getByRole("button", { name: /Dışa aktar$/ })).toBeEnabled()
  );

async function chooseDocx() {
  const item = (await screen.findAllByText(/DOCX olarak indir/))[0]!;
  await act(async () => {
    fireEvent.click(item);
  });
}

it("renders the trigger as the neutral companion of the primary edit action", () => {
  renderWithI18n(
    <ExportMenu
      documentId="d"
      revisionNo={3}
      kind="document"
      sourceFormat="markdown"
    />,
    "tr"
  );

  expect(screen.getByRole("button", { name: /Dışa aktar/ })).toHaveAttribute(
    "data-interactive-base-prominence",
    "secondary"
  );
});

it("downloads through the API with the server filename and revokes the URL", async () => {
  jest.mocked(exportRevision).mockResolvedValue({
    blob: new Blob(["x"]),
    filename: "Plan.docx",
  });
  open();
  await chooseDocx();

  await waitFor(() => expect(clicked).toHaveLength(1));
  expect(exportRevision).toHaveBeenCalledWith("d", 3, "docx");
  expect(clicked[0]).toEqual({ download: "Plan.docx", href: "blob:export" });
  await settled();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:export");
});

it("surfaces the server's message when the export is rejected", async () => {
  jest
    .mocked(exportRevision)
    .mockRejectedValue(new FetchError("Biçim desteklenmiyor", 422, {}));
  open();
  await chooseDocx();

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("Biçim desteklenmiyor")
  );
  await settled();
  expect(createObjectURL).not.toHaveBeenCalled();
});

it("uses the generic message for unknown failures and disables the trigger while busy", async () => {
  let reject: (e: Error) => void = () => {};
  jest
    .mocked(exportRevision)
    .mockReturnValue(new Promise((_, r) => (reject = r)));
  open();
  await chooseDocx();

  expect(
    await screen.findByRole("button", { name: /Dışa aktarılıyor/ })
  ).toBeDisabled();

  await act(async () => reject(new Error("network")));
  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("Doküman dışa aktarılamadı.")
  );
  expect(
    screen.getByRole("button", { name: /Dışa aktar$/ })
  ).not.toBeDisabled();
});
