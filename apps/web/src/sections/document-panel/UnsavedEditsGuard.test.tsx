import { act, fireEvent, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";
import { UnsavedEditsGuard } from "@/sections/document-panel/UnsavedEditsGuard";

const store = () => useDocumentPanelStore.getState();

function startDirtyEdit() {
  act(() => {
    store().openDocument("d", 2);
    store().editDraft(2, "# base");
    store().updateDraft("# base\nmine");
  });
}

function beforeUnloadEvent() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
}

beforeEach(() => useDocumentPanelStore.setState(initialDocumentPanelState));

it("renders nothing while no navigation is held back", () => {
  renderWithI18n(<UnsavedEditsGuard />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("asks before closing and discards on confirm", () => {
  renderWithI18n(<UnsavedEditsGuard />);
  startDirtyEdit();

  act(() => store().requestClose());
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(store().isOpen).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(store()).toMatchObject({ isOpen: false, edit: null });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps the edit when the user keeps editing", () => {
  renderWithI18n(<UnsavedEditsGuard />);
  startDirtyEdit();

  act(() => store().requestClose());
  fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));

  expect(store().edit?.text).toBe("# base\nmine");
  expect(store().isOpen).toBe(true);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("treats Escape as keep editing", () => {
  renderWithI18n(<UnsavedEditsGuard />);
  startDirtyEdit();

  act(() => store().requestClose());
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

  expect(store().edit).not.toBeNull();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

describe("beforeunload", () => {
  it("warns only while the edit has unsaved changes", () => {
    renderWithI18n(<UnsavedEditsGuard />);
    expect(beforeUnloadEvent().defaultPrevented).toBe(false);

    startDirtyEdit();
    expect(beforeUnloadEvent().defaultPrevented).toBe(true);

    act(() => store().updateDraft("# base"));
    expect(beforeUnloadEvent().defaultPrevented).toBe(false);
  });

  it("removes the listener on unmount", () => {
    const view = renderWithI18n(<UnsavedEditsGuard />);
    startDirtyEdit();
    view.unmount();
    expect(beforeUnloadEvent().defaultPrevented).toBe(false);
  });
});
