import { act, fireEvent, renderHook, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { CompareTab } from "@/sections/document-panel/CompareTab";
import { useProportionalScrollSync } from "@/sections/document-panel/useProportionalScrollSync";
import { useRevisionPair } from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";

jest.mock("@/lib/api/domains/documents/hooks");

const summary = (n: number) => ({ revision_no: n }) as never;
const doc = {
  document_id: "d",
  head_revision_no: 3,
  revisions: [summary(1), summary(2), summary(3)],
} as never;

beforeEach(() => {
  useDocumentPanelStore.setState(initialDocumentPanelState);
  useDocumentPanelStore.getState().openDocument("d", 3, "compare");
  jest.mocked(useRevisionPair).mockImplementation(
    (_d, l, r) =>
      ({
        left: {
          data: {
            revision_no: l,
            source_format: "markdown",
            content: "# A\n\nold\n\ngone",
          },
        },
        right: {
          data: {
            revision_no: r,
            source_format: "markdown",
            content: "# A\n\nnew\n\n## Added",
          },
        },
        isLoading: false,
        error: undefined,
      }) as never
  );
});

it("defaults to the previous draft vs the viewed draft with status classes", () => {
  renderWithI18n(<CompareTab document={doc} viewed={3} />, "tr");

  expect(useRevisionPair).toHaveBeenLastCalledWith("d", 2, 3);
  const left = screen.getByTestId("compare-left");
  const right = screen.getByTestId("compare-right");
  expect(
    Array.from(left.querySelectorAll("[data-testid=compare-block]")).map(
      (b) => (b as HTMLElement).dataset.status
    )
  ).toEqual(["same", "changed", "removed"]);
  expect(
    Array.from(right.querySelectorAll("[data-testid=compare-block]")).map(
      (b) => (b as HTMLElement).dataset.status
    )
  ).toEqual(["same", "changed", "added"]);
});

it("swaps sides", () => {
  renderWithI18n(<CompareTab document={doc} viewed={3} />, "tr");
  fireEvent.click(screen.getByRole("button", { name: "Yer değiştir" }));
  expect(useDocumentPanelStore.getState().compare).toEqual({
    left: 3,
    right: 2,
  });
});

describe("useProportionalScrollSync", () => {
  function scroller(scrollHeight: number) {
    const el = document.createElement("div");
    Object.defineProperty(el, "scrollHeight", { value: scrollHeight });
    Object.defineProperty(el, "clientHeight", { value: 100 });
    return el;
  }

  it("mirrors the scroll ratio and ignores its own echo", () => {
    const a = scroller(1100);
    const b = scroller(2100);
    renderHook(() => useProportionalScrollSync(a, b, true));

    act(() => {
      a.scrollTop = 500;
      a.dispatchEvent(new Event("scroll"));
    });
    expect(b.scrollTop).toBe(1000);

    act(() => {
      b.dispatchEvent(new Event("scroll"));
    });
    expect(a.scrollTop).toBe(500);
  });

  it("does not swallow a real scroll after a mirror that moved nothing", () => {
    const a = scroller(1100);
    const b = scroller(2100);
    renderHook(() => useProportionalScrollSync(a, b, true));

    // Both sides are already at the top: mirroring changes nothing, so the
    // browser fires no echo event for `b`.
    act(() => {
      a.dispatchEvent(new Event("scroll"));
    });

    act(() => {
      b.scrollTop = 1000;
      b.dispatchEvent(new Event("scroll"));
    });
    expect(a.scrollTop).toBe(500);
  });
});

it("shows a retryable error and keeps the pickers when a revision fails to load", () => {
  const retry = jest.fn();
  jest.mocked(useRevisionPair).mockReturnValue({
    left: {},
    right: {},
    isLoading: false,
    error: new Error("boom"),
    retry,
  } as never);
  renderWithI18n(<CompareTab document={doc} viewed={3} />, "tr");

  expect(screen.getByText("Doküman yüklenemedi.")).toBeInTheDocument();
  expect(screen.getByLabelText("Sol taslak")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Tekrar dene" }));
  expect(retry).toHaveBeenCalledTimes(1);
});
