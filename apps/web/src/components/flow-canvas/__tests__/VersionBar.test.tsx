/**
 * Tests for VersionBar. `useFlowVersions`/`useFlowValidation` are mocked
 * directly (this project's established pattern — Task 25/26/27 all mock
 * their data hooks the same way) so this file's own tests focus on UI
 * wiring: status label, permission gating, and error-handling affordances
 * (§10), not the hooks' own request/response logic (already covered by
 * useFlowVersions.test.tsx / useFlowValidation.test.tsx).
 *
 * `@/providers/UserProvider` is globally mocked (jest.config.js) to a
 * stub with no `hasAnyPermission` — overridden here per-file since
 * VersionBar calls it directly.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createFlowStore } from "../stores/flowStore";
import { VersionBar } from "../components/VersionBar";
import type { FlowVersion, PublishResult } from "../hooks/useFlowVersions";

const mockUseFlowVersions = jest.fn();
jest.mock("../hooks/useFlowVersions", () => ({
  useFlowVersions: (definitionId: string) => mockUseFlowVersions(definitionId),
}));

const mockSaveDraftNow = jest.fn();
jest.mock("../hooks/useFlowDraft", () => ({
  saveDraftNow: (...args: unknown[]) => mockSaveDraftNow(...args),
}));

const mockUseFlowValidation = jest.fn();
jest.mock("../hooks/useFlowValidation", () => ({
  useFlowValidation: (...args: unknown[]) => mockUseFlowValidation(...args),
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
    status: "draft",
    created_by: "user-1",
    published_by: null,
    created_at: null,
    published_at: null,
    notes: null,
    ...overrides,
  };
}

function mockVersionsHook(
  overrides: Partial<ReturnType<typeof baseVersionsHook>> = {}
) {
  const value = { ...baseVersionsHook(), ...overrides };
  mockUseFlowVersions.mockReturnValue(value);
  return value;
}

function baseVersionsHook() {
  return {
    versions: [] as FlowVersion[],
    isLoading: false,
    error: undefined,
    publishedVersion: null as FlowVersion | null,
    draftVersion: null as FlowVersion | null,
    publish: jest.fn<Promise<PublishResult>, [number | undefined]>(),
    rollback: jest.fn(),
    refresh: jest.fn(),
  };
}

beforeEach(() => {
  mockSaveDraftNow.mockReset();
  mockUseFlowVersions.mockReset();
  mockUseFlowValidation.mockReset();
  mockUseFlowValidation.mockReturnValue({ hasErrors: false });
  mockHasAnyPermission = jest.fn().mockReturnValue(true);
});

describe("VersionBar — 28.11, status label", () => {
  it("shows Draft when there is no published version", () => {
    mockVersionsHook({ publishedVersion: null });
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("version-status")).toHaveTextContent("Draft");
  });

  it("shows Published v{n} when published and no newer draft row exists", () => {
    mockVersionsHook({
      publishedVersion: version({ status: "published", version_no: 2 }),
      draftVersion: null,
    });
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("version-status")).toHaveTextContent(
      "Published v2"
    );
  });

  it("shows Draft ahead of v{n} when a draft row exists alongside a published one", () => {
    mockVersionsHook({
      publishedVersion: version({ status: "published", version_no: 2 }),
      draftVersion: version({ status: "draft", version_no: 3 }),
    });
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("version-status")).toHaveTextContent(
      "Draft ahead of v2"
    );
  });
});

describe("VersionBar — 28.8, publish gated by flow:publish", () => {
  it("does not render the publish button without the permission", () => {
    mockHasAnyPermission.mockReturnValue(false);
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.queryByTestId("publish-button")).not.toBeInTheDocument();
  });

  it("renders it enabled with the permission and no validation errors", () => {
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("publish-button")).not.toBeDisabled();
  });
});

describe("VersionBar — 28.9, validation errors block publish, warnings do not", () => {
  it("disables Publish when useFlowValidation reports errors", () => {
    mockUseFlowValidation.mockReturnValue({ hasErrors: true });
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("publish-button")).toBeDisabled();
  });

  it("does not disable Publish for a warnings-only result", () => {
    mockUseFlowValidation.mockReturnValue({ hasErrors: false });
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.getByTestId("publish-button")).not.toBeDisabled();
  });
});

describe("VersionBar — 28.6, publish 409 offers reload, preserves the local draft", () => {
  it("shows a conflict message and a reload-and-retry action without touching store.nodes", async () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "n1",
        type: "templateNode",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      },
    ]);
    const hook = mockVersionsHook({
      publish: jest.fn().mockResolvedValue({
        kind: "conflict",
        message: "Published concurrently.",
      }),
    });

    render(<VersionBar definitionId={DEFINITION_ID} store={store} />);
    fireEvent.click(screen.getByTestId("publish-button"));
    fireEvent.click(await screen.findByTestId("publish-modal-confirm"));

    expect(await screen.findByTestId("publish-conflict")).toHaveTextContent(
      "Published concurrently."
    );
    expect(store.getState().nodes).toHaveLength(1); // draft untouched

    fireEvent.click(screen.getByRole("button", { name: /reload and retry/i }));
    expect(hook.refresh).toHaveBeenCalled();
  });

  it("shows a translated default conflict message when the server sends no detail", async () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "n1",
        type: "templateNode",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      },
    ]);
    mockVersionsHook({
      publish: jest.fn().mockResolvedValue({ kind: "conflict", message: null }),
    });

    render(<VersionBar definitionId={DEFINITION_ID} store={store} />);
    fireEvent.click(screen.getByTestId("publish-button"));
    fireEvent.click(await screen.findByTestId("publish-modal-confirm"));

    expect(await screen.findByTestId("publish-conflict")).toHaveTextContent(
      "The flow was published concurrently."
    );
    expect(
      screen.getByRole("button", { name: /reload and retry/i })
    ).toBeInTheDocument();
  });
});

describe("VersionBar — 28.7, publish 400 maps issues onto their node_id", () => {
  it("shows each issue's node_id, not a raw undifferentiated list", async () => {
    mockVersionsHook({
      publish: jest.fn().mockResolvedValue({
        kind: "invalid",
        errors: [
          {
            code: "FLOW_UNKNOWN_COMPONENT",
            message: "Unknown component",
            node_id: "n1",
            edge_id: null,
          },
        ],
      }),
    });

    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    fireEvent.click(screen.getByTestId("publish-button"));
    fireEvent.click(await screen.findByTestId("publish-modal-confirm"));

    const issues = await screen.findByTestId("publish-issues");
    expect(issues).toHaveTextContent("Node n1");
    expect(issues).toHaveTextContent("Unknown component");
  });
});

describe("VersionBar — 45, history toggle hands the panel to the page", () => {
  it("invokes onToggleHistory when the history button is clicked", () => {
    const onToggleHistory = jest.fn();
    mockVersionsHook();
    render(
      <VersionBar
        definitionId={DEFINITION_ID}
        store={createFlowStore()}
        onToggleHistory={onToggleHistory}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /version history/i }));
    expect(onToggleHistory).toHaveBeenCalledTimes(1);
  });

  it("does not render the history toggle when the page provides none", () => {
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(
      screen.queryByRole("button", { name: /version history/i })
    ).not.toBeInTheDocument();
  });
});

describe("VersionBar — 45, publish success re-saves the published spec as the draft", () => {
  it("calls saveDraftNow then refreshes after a successful publish", async () => {
    const store = createFlowStore();
    const hook = mockVersionsHook({
      publish: jest.fn().mockResolvedValue({
        kind: "success",
        version: version({ status: "published" }),
      } satisfies PublishResult),
    });

    render(<VersionBar definitionId={DEFINITION_ID} store={store} />);
    fireEvent.click(screen.getByTestId("publish-button"));
    fireEvent.click(await screen.findByTestId("publish-modal-confirm"));

    await waitFor(() =>
      expect(mockSaveDraftNow).toHaveBeenCalledWith(DEFINITION_ID, store)
    );
    await waitFor(() => expect(hook.refresh).toHaveBeenCalled());
  });

  it("keeps the publish result successful even when the draft re-save fails", async () => {
    mockSaveDraftNow.mockRejectedValue(new Error("network"));
    mockVersionsHook({
      publish: jest.fn().mockResolvedValue({
        kind: "success",
        version: version({ status: "published" }),
      } satisfies PublishResult),
    });

    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    fireEvent.click(screen.getByTestId("publish-button"));
    fireEvent.click(await screen.findByTestId("publish-modal-confirm"));

    // No conflict/issues UI and no unhandled rejection — a failed re-save
    // must not look like a failed publish.
    await waitFor(() => expect(mockSaveDraftNow).toHaveBeenCalled());
    expect(screen.queryByTestId("publish-conflict")).not.toBeInTheDocument();
    expect(screen.queryByTestId("publish-issues")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("publish-button")).not.toBeDisabled()
    );
  });
});

describe("VersionBar — unsaved-changes indicator", () => {
  it("shows an unsaved indicator when the store is dirty", () => {
    const store = createFlowStore();
    store.getState().setNodes([
      {
        id: "n1",
        type: "templateNode",
        position: { x: 0, y: 0 },
        data: { type: "ChatInput", templateVersion: 1, values: {} },
      },
    ]);
    mockVersionsHook();
    render(<VersionBar definitionId={DEFINITION_ID} store={store} />);
    expect(screen.getByTestId("unsaved-indicator")).toBeInTheDocument();
  });

  it("hides it when the store is clean", () => {
    mockVersionsHook();
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );
    expect(screen.queryByTestId("unsaved-indicator")).not.toBeInTheDocument();
  });
});

describe("VersionBar — flow studio chrome (exit, status-chip history, publish menu)", () => {
  it("calls onExit when the back button is pressed", () => {
    const onExit = jest.fn();
    mockVersionsHook({
      publishedVersion: version({ status: "published", version_no: 3 }),
    });
    render(
      <VersionBar
        definitionId={DEFINITION_ID}
        store={createFlowStore()}
        onExit={onExit}
      />
    );

    fireEvent.click(screen.getByTestId("flow-studio-exit"));
    expect(onExit).toHaveBeenCalled();
  });

  it("shows the status as a label, not a second way to open history", () => {
    mockVersionsHook({
      publishedVersion: version({ status: "published", version_no: 3 }),
    });
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );

    // The history icon button is the single history affordance; the chip
    // next to the flow name only reports state.
    const chip = screen.getByTestId("flow-studio-status-chip");
    expect(chip.tagName).not.toBe("BUTTON");
    expect(chip.querySelector("button")).toBeNull();
  });

  it("offers exactly one publish control — no split-button dropdown", () => {
    mockVersionsHook({
      draftVersion: version({ status: "draft", version_no: 1 }),
    });
    render(
      <VersionBar definitionId={DEFINITION_ID} store={createFlowStore()} />
    );

    expect(screen.getByTestId("publish-button")).toBeInTheDocument();
    expect(
      screen.queryByTestId("flow-studio-publish-menu")
    ).not.toBeInTheDocument();
    // Import lives on its own icon button; it must not also be a menu row.
    expect(screen.getByTestId("import-flow-trigger")).toBeInTheDocument();
    expect(
      screen.queryByTestId("flow-studio-menu-import")
    ).not.toBeInTheDocument();
  });

  it("opens settings when the agent name is clicked", () => {
    const onOpenSettings = jest.fn();
    mockVersionsHook();
    render(
      <VersionBar
        definitionId={DEFINITION_ID}
        store={createFlowStore()}
        agent={
          { id: 1, name: "Fatura Akışı", description: "", tools: [] } as any
        }
        onOpenSettings={onOpenSettings}
      />
    );

    fireEvent.click(screen.getByTestId("flow-studio-open-settings"));
    expect(onOpenSettings).toHaveBeenCalled();
  });
});
