import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { toast } from "@/hooks/useToast";
import { FetchError } from "@/lib/api/http/errors";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { EditTab } from "@/sections/document-panel/EditTab";
import {
  DiagramInvalidError,
  RevisionConflictError,
  saveUserRevision,
} from "@/lib/api/domains/documents/api";
import { useRevision } from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";

jest.mock("@/lib/api/domains/documents/api", () => ({
  ...jest.requireActual("@/lib/api/domains/documents/api"),
  saveUserRevision: jest.fn(),
}));
jest.mock("@/lib/api/domains/documents/hooks", () => ({
  useRevision: jest.fn(),
  refreshAuthoredDocument: jest.fn(),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
jest.mock("@/sections/document-panel/LazyCodeEditor", () => ({
  LazyCodeEditor: (p: {
    value: string;
    onChange: (v: string) => void;
    highlightLines?: number[];
    mergeOriginal?: string | null;
  }) => (
    <textarea
      aria-label="source"
      value={p.value}
      data-highlight={(p.highlightLines ?? []).join(",")}
      data-original={p.mergeOriginal ?? ""}
      onChange={(e) => p.onChange(e.target.value)}
    />
  ),
}));

const doc = { document_id: "d", head_revision_no: 3, revisions: [] } as never;
const store = () => useDocumentPanelStore.getState();

beforeEach(() => {
  jest.clearAllMocks();
  useDocumentPanelStore.setState(initialDocumentPanelState);
  store().openDocument("d", 3);
  store().syncHead("d", 3);
  store().editDraft(3, "# Başlık");
  jest.mocked(useRevision).mockImplementation(
    (_d, no) =>
      ({
        data: no
          ? {
              revision_no: no,
              source_format: "markdown",
              content: `# Taslak ${no}`,
            }
          : undefined,
      }) as never
  );
});

const type = (value: string) =>
  fireEvent.change(screen.getByLabelText("source"), { target: { value } });
const save = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Yeni taslak olarak kaydet" })
  );

it("keeps the text in the store across a remount", () => {
  const view = renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Benim metnim");
  view.unmount();
  renderWithI18n(<EditTab document={doc} />, "tr");
  expect(screen.getByLabelText("source")).toHaveValue("# Benim metnim");
});

it("saves as a new draft on the base revision", async () => {
  jest
    .mocked(saveUserRevision)
    .mockResolvedValue({ revision: { revision_no: 4 } } as never);
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Yeni");
  save();

  await waitFor(() => expect(store().edit).toBeNull());
  expect(saveUserRevision).toHaveBeenCalledWith("d", {
    baseRevisionNo: 3,
    content: "# Yeni",
  });
  expect(store()).toMatchObject({ revisionNo: 4, tab: "preview" });
});

it("on 409 keeps the text and overwrites the head after a confirmation", async () => {
  jest
    .mocked(saveUserRevision)
    .mockRejectedValueOnce(new RevisionConflictError(5))
    .mockResolvedValueOnce({ revision: { revision_no: 6 } } as never);
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Benim");
  save();

  expect(
    await screen.findByText(
      "Siz düzenlerken Taslak 5 oluşturuldu. Değişiklikleriniz Taslak 3 üzerinde yapıldı."
    )
  ).toBeInTheDocument();
  expect(screen.getByLabelText("source")).toHaveValue("# Benim");

  fireEvent.click(
    screen.getByRole("button", { name: "Benim sürümümle üzerine yaz" })
  );
  expect(saveUserRevision).toHaveBeenCalledTimes(1);
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", {
      name: "Üzerine yaz",
    })
  );
  await waitFor(() => expect(store().revisionNo).toBe(6));
  expect(jest.mocked(saveUserRevision).mock.calls[1]).toEqual([
    "d",
    { baseRevisionNo: 5, content: "# Benim" },
  ]);
});

it("on 409 can apply the text on the latest draft with a merge view", async () => {
  jest
    .mocked(saveUserRevision)
    .mockRejectedValueOnce(new RevisionConflictError(5));
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Benim");
  save();

  fireEvent.click(
    await screen.findByRole("button", { name: "Taslak 5 üzerine uygula" })
  );

  expect(screen.getByLabelText("source")).toHaveAttribute(
    "data-original",
    "# Taslak 5"
  );
  expect(screen.getByLabelText("source")).toHaveValue("# Benim");
  expect(
    screen.getByText(/Taslak 5 ile farklar işaretlendi/)
  ).toBeInTheDocument();
  expect(store().edit).toMatchObject({ baseRevisionNo: 5, mergeWith: 5 });
});

it("on 422 highlights and lists the diagram lines", async () => {
  jest
    .mocked(saveUserRevision)
    .mockRejectedValueOnce(
      new DiagramInvalidError([
        { block_index: 0, document_line: 12, line: 3, message: "Parse error" },
      ])
    );
  renderWithI18n(<EditTab document={doc} />, "tr");
  save();

  expect(
    await screen.findByText("1 diyagram hatalı; işaretli satırları düzeltin.")
  ).toBeInTheDocument();
  expect(screen.getByText("Satır 12: Parse error")).toBeInTheDocument();
  expect(screen.getByLabelText("source")).toHaveAttribute(
    "data-highlight",
    "12"
  );
});

it("debounces the live preview", () => {
  jest.useFakeTimers();
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Canlı");
  expect(
    screen.queryByRole("heading", { name: "Canlı" })
  ).not.toBeInTheDocument();
  act(() => jest.advanceTimersByTime(300));
  expect(screen.getByRole("heading", { name: "Canlı" })).toBeInTheDocument();
  jest.useRealTimers();
});

it("cancel discards the session", () => {
  renderWithI18n(<EditTab document={doc} />, "tr");
  fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
  expect(store().edit).toBeNull();
});

it("cancel on unsaved changes asks first instead of discarding", () => {
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Değişti");
  fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
  expect(store().edit).not.toBeNull();
  expect(store().pendingDiscard).not.toBeNull();
});

it("shows the server message for other save rejections", async () => {
  jest
    .mocked(saveUserRevision)
    .mockRejectedValueOnce(
      new FetchError("Geçersiz içerik: dosya çok büyük", 422, {})
    );
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Yeni");
  save();

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("Geçersiz içerik: dosya çok büyük")
  );
});

it("falls back to the generic message for unknown save failures", async () => {
  jest.mocked(saveUserRevision).mockRejectedValueOnce(new Error("network"));
  renderWithI18n(<EditTab document={doc} />, "tr");
  type("# Yeni");
  save();

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("Taslak kaydedilemedi.")
  );
});

describe("editing a draft that is already older than the head", () => {
  beforeEach(() => {
    useDocumentPanelStore.setState(initialDocumentPanelState);
    store().openDocument("d", 2);
    store().syncHead("d", 4);
    store().editDraft(2, "# Taslak 2");
  });

  it("warns before the user starts typing", () => {
    renderWithI18n(<EditTab document={doc} />, "tr");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Taslak 2 üzerinde düzenliyorsunuz ama Taslak 4 daha yeni."
    );
  });

  it("words the conflict as already stale, not as created while editing", async () => {
    jest
      .mocked(saveUserRevision)
      .mockRejectedValueOnce(new RevisionConflictError(4));
    renderWithI18n(<EditTab document={doc} />, "tr");
    type("# Benim");
    save();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("zaten eskiydi");
    expect(alert).not.toHaveTextContent("Siz düzenlerken");
  });
});

it("does not warn when editing the head", () => {
  renderWithI18n(<EditTab document={doc} />, "tr");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
