import React from "react";
import { act, fireEvent, renderHook, screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentWorkspace } from "@/sections/document-panel/DocumentWorkspace";
import { usePanelSidebarExclusivity } from "@/sections/document-panel/usePanelSidebarExclusivity";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";

jest.mock("react-resizable-panels", () => ({
  Group: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="group">{children}</div>
  ),
  Panel: ({
    children,
    id,
    onResize,
  }: {
    children: React.ReactNode;
    id: string;
    onResize?: (size: { asPercentage: number; inPixels: number }) => void;
  }) => {
    if (id === "chat") chatResize = onResize;
    return <div data-testid={`panel-${id}`}>{children}</div>;
  },
  Separator: () => <div data-testid="separator" />,
  usePanelRef: () => ({
    current: {
      collapse: jest.fn(),
      expand: jest.fn(),
      isCollapsed: () => false,
    },
  }),
}));

let chatResize:
  | ((size: { asPercentage: number; inPixels: number }) => void)
  | undefined;
let mounts = 0;
function Chat() {
  React.useEffect(() => {
    mounts += 1;
  }, []);
  return <div>chat</div>;
}

beforeEach(() => {
  mounts = 0;
  useDocumentPanelStore.setState(initialDocumentPanelState);
});

it("adds the document panel on desktop without remounting the chat", () => {
  renderWithI18n(
    <DocumentWorkspace
      isMobile={false}
      renderPanel={() => <div>panel body</div>}
    >
      <Chat />
    </DocumentWorkspace>
  );
  expect(screen.queryByTestId("panel-document")).not.toBeInTheDocument();
  expect(useDocumentPanelStore.getState().hostMounted).toBe(true);

  act(() => useDocumentPanelStore.getState().openDocument("d"));

  expect(screen.getByTestId("panel-document")).toHaveTextContent("panel body");
  expect(screen.getByTestId("separator")).toBeInTheDocument();
  expect(mounts).toBe(1);
});

describe("mobile sheet", () => {
  const renderSheet = () =>
    renderWithI18n(
      <DocumentWorkspace
        isMobile
        renderPanel={() => <button type="button">panel action</button>}
      >
        <Chat />
      </DocumentWorkspace>
    );

  it("is a labelled modal dialog, not a bare div", () => {
    renderSheet();
    act(() => useDocumentPanelStore.getState().openDocument("d"));

    const dialog = screen.getByRole("dialog", { name: "Document" });
    expect(dialog).toHaveTextContent("panel action");
    expect(screen.queryByTestId("separator")).not.toBeInTheDocument();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("closes on Escape", () => {
    renderSheet();
    act(() => useDocumentPanelStore.getState().openDocument("d"));

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(useDocumentPanelStore.getState().isOpen).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks before Escape drops an unsaved edit", () => {
    renderSheet();
    act(() => {
      const store = useDocumentPanelStore.getState();
      store.openDocument("d", 2);
      store.editDraft(2, "a");
      store.updateDraft("b");
    });

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(useDocumentPanelStore.getState().isOpen).toBe(true);
    expect(useDocumentPanelStore.getState().pendingDiscard).not.toBeNull();
  });
});

it("follows the chat panel size, so dragging the separator updates maximize", () => {
  renderWithI18n(
    <DocumentWorkspace
      isMobile={false}
      renderPanel={({ maximized }) => <div>{`maximized:${maximized}`}</div>}
    >
      <Chat />
    </DocumentWorkspace>
  );
  act(() => useDocumentPanelStore.getState().openDocument("d"));
  expect(screen.getByText("maximized:false")).toBeInTheDocument();

  act(() => chatResize?.({ asPercentage: 0, inPixels: 0 }));
  expect(screen.getByText("maximized:true")).toBeInTheDocument();

  act(() => chatResize?.({ asPercentage: 40, inPixels: 500 }));
  expect(screen.getByText("maximized:false")).toBeInTheDocument();
});

it("clears hostMounted on unmount", () => {
  const view = renderWithI18n(
    <DocumentWorkspace isMobile={false} renderPanel={() => null}>
      <Chat />
    </DocumentWorkspace>
  );
  view.unmount();
  expect(useDocumentPanelStore.getState().hostMounted).toBe(false);
});

describe("usePanelSidebarExclusivity", () => {
  it("keeps the panel and hides the sources again when the user keeps a dirty edit", () => {
    const setSidebar = jest.fn();
    const { rerender } = renderHook(
      ({ visible }) => usePanelSidebarExclusivity(visible, setSidebar),
      { initialProps: { visible: false } }
    );
    act(() => {
      const store = useDocumentPanelStore.getState();
      store.openDocument("d", 2);
      store.editDraft(2, "a");
      store.updateDraft("b");
    });
    rerender({ visible: false });
    setSidebar.mockClear();

    rerender({ visible: true });
    expect(useDocumentPanelStore.getState().isOpen).toBe(true);

    act(() => useDocumentPanelStore.getState().keepEditing());
    expect(setSidebar).toHaveBeenCalledWith(false);
  });

  it("closes the panel when sources open and hides sources when the panel opens", () => {
    const setSidebar = jest.fn();
    const { rerender } = renderHook(
      ({ visible }) => usePanelSidebarExclusivity(visible, setSidebar),
      { initialProps: { visible: false } }
    );

    act(() => useDocumentPanelStore.getState().openDocument("d"));
    rerender({ visible: false });
    expect(setSidebar).toHaveBeenCalledWith(false);

    rerender({ visible: true });
    expect(useDocumentPanelStore.getState().isOpen).toBe(false);
  });
});
