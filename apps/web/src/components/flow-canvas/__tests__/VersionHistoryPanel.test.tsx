/**
 * Tests for VersionHistoryPanel (Task 45 — ported from Langflow's
 * FlowVersionSidebar). `useFlowVersions` is mocked directly (this
 * project's established pattern — see VersionBar.test.tsx) so these tests
 * cover the panel's own wiring: row rendering, the read-only preview cycle
 * (snapshot → load → back-to-draft restore incl. wasDirty), restore with an
 * inline confirm, export, and permission gating.
 *
 * Brief: .tmp/flow-canvas-task-45-brief.md
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import { createFlowStore } from "../stores/flowStore";
import { VersionHistoryPanel } from "../components/VersionHistoryPanel";
import type { FlowVersion, FlowVersionDetail } from "../hooks/useFlowVersions";

const mockUseFlowVersions = jest.fn();
jest.mock("../hooks/useFlowVersions", () => ({
  useFlowVersions: (definitionId: string) => mockUseFlowVersions(definitionId),
}));

let mockHasAnyPermission: jest.Mock;
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ hasAnyPermission: mockHasAnyPermission }),
}));

const DEFINITION_ID = "11111111-1111-1111-1111-111111111111";

function version(overrides: Partial<FlowVersion> = {}): FlowVersion {
  return {
    id: "v1",
    definition_id: DEFINITION_ID,
    version_no: 1,
    status: "published",
    created_by: "user-1",
    published_by: "user-1",
    created_at: "2026-08-01T10:00:00Z",
    published_at: "2026-08-01T10:05:00Z",
    notes: null,
    ...overrides,
  };
}

function versionDetail(versionNo: number): FlowVersionDetail {
  return {
    ...version({
      id: `vd${versionNo}`,
      version_no: versionNo,
      status: "published",
    }),
    flow_spec: {
      version: "1",
      nodes: [
        {
          id: `hist-${versionNo}`,
          type: "ChatInput",
          template_version: 1,
          position: { x: 10, y: 20 },
          values: {},
        },
      ],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
    },
  };
}

function baseHook() {
  return {
    versions: [] as FlowVersion[],
    isLoading: false,
    error: undefined as Error | undefined,
    publishedVersion: null as FlowVersion | null,
    draftVersion: null as FlowVersion | null,
    publish: jest.fn(),
    rollback: jest.fn(),
    refresh: jest.fn(),
    getVersionDetail: jest.fn(),
  };
}

function mockHook(overrides: Partial<ReturnType<typeof baseHook>> = {}) {
  const value = { ...baseHook(), ...overrides };
  mockUseFlowVersions.mockReturnValue(value);
  return value;
}

const i18n = createI18nInstance("en");

function renderPanel(store = createFlowStore(), open = true) {
  const onClose = jest.fn();
  render(
    <I18nextProvider i18n={i18n}>
      <VersionHistoryPanel
        definitionId={DEFINITION_ID}
        store={store}
        open={open}
        onClose={onClose}
      />
    </I18nextProvider>
  );
  return { store, onClose };
}

beforeEach(() => {
  mockUseFlowVersions.mockReset();
  mockHasAnyPermission = jest.fn().mockReturnValue(true);
});

describe("VersionHistoryPanel — 45.1, rows", () => {
  it("pins the draft row and lists published/archived versions only", () => {
    mockHook({
      versions: [
        version({
          id: "v3",
          version_no: 3,
          status: "draft",
          published_at: null,
        }),
        version({ id: "v2", version_no: 2, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
      draftVersion: version({
        id: "v3",
        version_no: 3,
        status: "draft",
        published_at: null,
      }),
    });
    renderPanel();

    expect(screen.getByTestId("version-current-draft")).toBeInTheDocument();
    expect(screen.getByTestId("version-row-2")).toBeInTheDocument();
    expect(screen.getByTestId("version-row-1")).toBeInTheDocument();
    // The draft is the pinned row — it must not also appear as v3.
    expect(screen.queryByTestId("version-row-3")).not.toBeInTheDocument();
    expect(screen.getByTestId("version-history-count")).toHaveTextContent("2");
  });

  it("shows the empty state when only a draft exists", () => {
    mockHook({
      versions: [
        version({
          id: "v1",
          version_no: 1,
          status: "draft",
          published_at: null,
        }),
      ],
    });
    renderPanel();
    expect(screen.getByTestId("version-history-empty")).toHaveTextContent(
      "No published versions yet."
    );
  });

  it("offers retry when the version list fails to load", () => {
    const hook = mockHook({ error: new Error("boom") });
    renderPanel();
    expect(screen.getByText("Failed to load versions.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(hook.refresh).toHaveBeenCalled();
  });

  it("shows a loading state while versions load", () => {
    mockHook({ isLoading: true });
    renderPanel();
    expect(screen.getByTestId("version-history-loading")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    mockHook({ isLoading: true });
    renderPanel(createFlowStore(), false);
    expect(
      screen.queryByTestId("version-history-panel")
    ).not.toBeInTheDocument();
  });
});

describe("VersionHistoryPanel — 45.2, read-only preview cycle", () => {
  it("previews a version, then restores the draft snapshot with its dirty flag", async () => {
    const store = createFlowStore();
    // A real edit before previewing: setNodes dirties the store (Task 24.8).
    store.getState().setNodes([
      {
        id: "work-1",
        type: "templateNode",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      },
    ]);
    expect(store.getState().isDirty).toBe(true);

    const hook = mockHook({
      versions: [version({ id: "v2", version_no: 2, status: "published" })],
      getVersionDetail: jest.fn().mockResolvedValue(versionDetail(2)),
    });
    renderPanel(store);

    fireEvent.click(screen.getByTestId("version-actions-2"));
    // LineItem renders a hidden accessibility mirror of its text — click
    // the first (visible) match, same pattern as VersionBar's old tests.
    fireEvent.click(screen.getAllByText("Preview on canvas")[0]!);

    await screen.findByTestId("version-preview-banner");
    expect(hook.getVersionDetail).toHaveBeenCalledWith(2);
    expect(store.getState().isPreviewMode).toBe(true);
    // Preview must never dirty the store — that would autosave the
    // historical spec over the user's draft (the panel's core invariant).
    expect(store.getState().isDirty).toBe(false);
    expect(store.getState().nodes.map((n) => n.id)).toEqual(["hist-2"]);

    fireEvent.click(screen.getByTestId("back-to-draft"));

    expect(store.getState().isPreviewMode).toBe(false);
    expect(store.getState().nodes.map((n) => n.id)).toEqual(["work-1"]);
    // Unsaved edits resume autosaving — the snapshot restores wasDirty too.
    expect(store.getState().isDirty).toBe(true);
    expect(
      screen.queryByTestId("version-preview-banner")
    ).not.toBeInTheDocument();
  });

  it("surfaces a friendly error when the version detail is gone (404)", async () => {
    const store = createFlowStore();
    mockHook({
      versions: [version({ id: "v2", version_no: 2, status: "published" })],
      getVersionDetail: jest.fn().mockResolvedValue(null),
    });
    renderPanel(store);

    fireEvent.click(screen.getByTestId("version-actions-2"));
    fireEvent.click(screen.getAllByText("Preview on canvas")[0]!);

    await screen.findByTestId("version-history-message");
    expect(screen.getByTestId("version-history-message")).toHaveTextContent(
      "no longer available"
    );
    expect(store.getState().isPreviewMode).toBe(false);
  });
});

describe("VersionHistoryPanel — 45.3, restore", () => {
  it("restores through an inline confirm and reports the new version", async () => {
    const hook = mockHook({
      versions: [
        version({ id: "v2", version_no: 2, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
      rollback: jest
        .fn()
        .mockResolvedValue(
          version({ id: "v3", version_no: 3, status: "published" })
        ),
    });
    renderPanel();

    fireEvent.click(screen.getByTestId("version-actions-1"));
    fireEvent.click(screen.getAllByText("Restore This Version")[0]!);
    expect(screen.getByTestId("restore-confirm")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("restore-confirm-button"));

    await waitFor(() => expect(hook.rollback).toHaveBeenCalledWith(1));
    expect(
      await screen.findByText("Restored v1 — now published as v3.")
    ).toBeInTheDocument();
  });

  it("hides Restore without flow:publish (archived rows keep Preview/Export)", () => {
    mockHasAnyPermission.mockReturnValue(false);
    mockHook({
      versions: [
        version({ id: "v2", version_no: 2, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
    });
    renderPanel();

    fireEvent.click(screen.getByTestId("version-actions-1"));
    expect(screen.getAllByText("Preview on canvas").length).toBeGreaterThan(0);
    expect(screen.queryByText("Restore This Version")).not.toBeInTheDocument();
  });
});

describe("VersionHistoryPanel — 45.4, export", () => {
  it("downloads the stored historical spec as JSON", async () => {
    const hook = mockHook({
      versions: [version({ id: "v2", version_no: 2, status: "published" })],
      getVersionDetail: jest.fn().mockResolvedValue(versionDetail(2)),
    });
    const createObjectURL = jest.fn().mockReturnValue("blob:mock");
    const revokeObjectURL = jest.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      configurable: true,
      writable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      configurable: true,
      writable: true,
    });
    const clickSpy = jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    renderPanel();
    fireEvent.click(screen.getByTestId("version-actions-2"));
    fireEvent.click(screen.getAllByText("Export JSON")[0]!);

    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(2));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
    clickSpy.mockRestore();
  });
});

describe("VersionHistoryPanel — version diff", () => {
  it("shows what changed in the draft since the last published version", async () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "new-node",
        type: "templateNode",
        position: { x: 0, y: 0 },
        data: { type: "ChatOutput", templateVersion: 1, values: {} },
      },
    ]);
    store.getState().resetDirty();

    const published = version({ id: "v2", version_no: 2, status: "published" });
    const hook = mockHook({
      versions: [published],
      publishedVersion: published,
      getVersionDetail: jest.fn().mockResolvedValue({
        ...published,
        flow_spec: {
          version: "1",
          nodes: [],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
      }),
    });

    renderPanel(store);
    fireEvent.click(screen.getByTestId("version-current-draft"));

    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(2));
    expect(await screen.findByTestId("version-diff-list")).toHaveTextContent(
      "node added"
    );
  });

  it("shows what changed between a version and the one before it", async () => {
    const v1 = version({ id: "v1", version_no: 1, status: "published" });
    const v2 = version({ id: "v2", version_no: 2, status: "published" });
    const hook = mockHook({
      versions: [v2, v1],
      getVersionDetail: jest.fn((versionNo: number) =>
        Promise.resolve(
          versionNo === 1
            ? {
                ...v1,
                flow_spec: {
                  version: "1",
                  nodes: [],
                  edges: [],
                  viewport: null,
                },
              }
            : versionDetail(2)
        )
      ),
    });

    renderPanel();
    fireEvent.click(screen.getByTestId("version-actions-2"));
    fireEvent.click(screen.getAllByText("Compare with previous")[0]!);

    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(1));
    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(2));
    expect(await screen.findByTestId("version-diff-list")).toHaveTextContent(
      "node added"
    );
  });

  it("treats a version with no predecessor as entirely new", async () => {
    const v1 = version({ id: "v1", version_no: 1, status: "published" });
    const hook = mockHook({
      versions: [v1],
      getVersionDetail: jest.fn().mockResolvedValue(versionDetail(1)),
    });

    renderPanel();
    fireEvent.click(screen.getByTestId("version-actions-1"));
    fireEvent.click(screen.getAllByText("Compare with previous")[0]!);

    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(1));
    expect(await screen.findByTestId("version-diff-list")).toHaveTextContent(
      "node added"
    );
  });
});

describe("VersionHistoryPanel — comparing two arbitrary (non-adjacent) versions", () => {
  it("shows selection checkboxes and a hint once compare mode is toggled on", () => {
    mockHook({
      versions: [
        version({ id: "v3", version_no: 3, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
    });
    renderPanel();

    expect(
      screen.queryByTestId("version-compare-hint")
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("version-compare-mode-toggle"));

    expect(screen.getByTestId("version-compare-hint")).toHaveTextContent(
      "Select a version to compare."
    );
    expect(screen.getByTestId("version-compare-select-3")).toBeInTheDocument();
    expect(screen.getByTestId("version-compare-select-1")).toBeInTheDocument();
    // The normal per-row "..." action menu is replaced while in this mode.
    expect(screen.queryByTestId("version-actions-3")).not.toBeInTheDocument();
  });

  it("diffs the two selected versions oldest-first, regardless of click order", async () => {
    const v1 = version({ id: "v1", version_no: 1, status: "archived" });
    const v5 = version({ id: "v5", version_no: 5, status: "published" });
    const hook = mockHook({
      versions: [v5, v1],
      getVersionDetail: jest.fn((versionNo: number) =>
        Promise.resolve(
          versionNo === 1
            ? {
                ...v1,
                flow_spec: {
                  version: "1",
                  nodes: [],
                  edges: [],
                  viewport: null,
                },
              }
            : versionDetail(5)
        )
      ),
    });
    renderPanel();

    fireEvent.click(screen.getByTestId("version-compare-mode-toggle"));
    // Click the *newer* one first — the diff must still run old→new.
    fireEvent.click(screen.getByTestId("version-compare-select-5"));
    fireEvent.click(screen.getByTestId("version-compare-select-1"));

    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(1));
    await waitFor(() => expect(hook.getVersionDetail).toHaveBeenCalledWith(5));
    // Accordion opens under the newer row (v5), keyed that way.
    expect(
      await screen.findByTestId("version-diff-accordion-5")
    ).toHaveTextContent("node added");
  });

  it("deselects a row on a second click instead of leaving it stuck selected", () => {
    mockHook({
      versions: [
        version({ id: "v3", version_no: 3, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
    });
    renderPanel();

    fireEvent.click(screen.getByTestId("version-compare-mode-toggle"));
    fireEvent.click(screen.getByTestId("version-compare-select-3"));
    expect(screen.getByTestId("version-compare-select-3")).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    fireEvent.click(screen.getByTestId("version-compare-select-3"));
    expect(screen.getByTestId("version-compare-select-3")).toHaveAttribute(
      "aria-pressed",
      "false"
    );
  });

  it("clears the selection and restores the normal row actions when compare mode is turned off", () => {
    mockHook({
      versions: [
        version({ id: "v3", version_no: 3, status: "published" }),
        version({ id: "v1", version_no: 1, status: "archived" }),
      ],
    });
    renderPanel();

    fireEvent.click(screen.getByTestId("version-compare-mode-toggle"));
    fireEvent.click(screen.getByTestId("version-compare-select-3"));
    fireEvent.click(screen.getByTestId("version-compare-mode-toggle"));

    expect(
      screen.queryByTestId("version-compare-select-3")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("version-actions-3")).toBeInTheDocument();
  });
});
