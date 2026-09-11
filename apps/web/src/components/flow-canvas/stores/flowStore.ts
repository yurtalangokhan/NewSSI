import type { NodeExecutionData } from "../types/execution";
/**
 * Ported from Langflow (MIT) — src/frontend/src/stores/flowStore.ts +
 * src/frontend/src/stores/flowsManagerStore.ts
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx:
 * - Node data is values-only (FlowNodeData) — see types/flow.ts's header
 *   for why. This is the single biggest divergence from upstream.
 * - Undo/redo (Langflow: flowsManagerStore, keyed per flowId because many
 *   flows can be open in memory at once) is consolidated directly into
 *   this store and NOT keyed per flow — one flow-canvas store instance
 *   exists per mounted canvas (one agent definition per route), so
 *   Langflow's multi-flow history keying is unneeded complexity.
 * - `paste`'s edge handling is simplified: Langflow encodes a structured
 *   descriptor into sourceHandle/targetHandle strings and has to re-encode
 *   it on paste; our handles are already plain port-name strings, so
 *   re-pointing source/target ids is enough.
 * - Consolidates what upstream splits across 8+ stores (alertStore,
 *   utilityStore, etc. are dropped — see .tmp/flow-canvas-port-triage.md).
 *
 * Brief: .tmp/flow-canvas-task-21-brief.md
 */

import {
  applyEdgeChanges,
  applyNodeChanges,
  type EdgeChange,
  type NodeChange,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import { cloneDeep } from "lodash";
import { createStore, type StoreApi } from "zustand";
import type {
  CanvasEdge,
  CanvasNode,
  ValidationIssue,
  Viewport,
} from "../types/flow";
import { getNodeId } from "../utils/reactflowUtils";
import { NOTE_COMPONENT_TYPE, RendererNodeType } from "../nodes/nodeTypes";

const DEFAULT_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };

const MAX_HISTORY_SIZE = 100;

// Where a note lands when added from the toolbar (no drop point): a fixed
// origin plus a little random jitter so repeated adds don't stack exactly.
const NOTE_DROP_ORIGIN = 250;
const NOTE_DROP_JITTER = 50;

type HistoryEntry = { nodes: CanvasNode[]; edges: CanvasEdge[] };

type PastePosition = { x: number; y: number };
type PasteSelection = { nodes: CanvasNode[]; edges: CanvasEdge[] };

export type { NodeExecutionData } from "../types/execution";
export type NodeRunStatus = {
  status: "queued" | "running" | "done" | "error";
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
  tokenCount: number | null;
};

export type FlowStore = {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  onNodesChange: (changes: NodeChange<CanvasNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<CanvasEdge>[]) => void;
  setNodes: (
    update: CanvasNode[] | ((nodes: CanvasNode[]) => CanvasNode[])
  ) => void;
  setEdges: (
    update: CanvasEdge[] | ((edges: CanvasEdge[]) => CanvasEdge[])
  ) => void;

  /** Task 28: autosave needs the current pan/zoom to round-trip through
   * `compile.ts`'s `toFlowSpec`. Updated from `FlowCanvas`'s `onMoveEnd`;
   * loaded from a fetched draft on mount. Restoring xyflow's actual
   * viewport-on-load (vs. `fitView`'s default "show everything") is out
   * of this task's TDD list — this only makes sure a save immediately
   * after load doesn't silently reset a saved pan/zoom to the origin. */
  viewport: Viewport;
  setViewport: (viewport: Viewport) => void;

  /** Task 28: written by `useFlowValidation` after each debounced
   * `/validate-flow` call, keyed by `node_id`. `TemplateNode` (Task 26)
   * reads its own entry reactively to paint itself — routing each issue
   * to its node (design spec §10) rather than a raw list, without a new
   * prop threaded through `nodeTypes`'s factory. */
  nodeErrors: Record<string, ValidationIssue[]>;
  setNodeErrors: (nodeErrors: Record<string, ValidationIssue[]>) => void;

  nodeRunStatus: Record<string, NodeRunStatus>;
  setNodeRunStatus: (nodeRunStatus: Record<string, NodeRunStatus>) => void;
  updateNodeRunStatus: (nodeId: string, patch: Partial<NodeRunStatus>) => void;
  resetNodeRunStatus: () => void;
  nodeExecutionData: Record<string, NodeExecutionData>;
  setNodeExecutionData: (
    nodeExecutionData: Record<string, NodeExecutionData>
  ) => void;
  resetNodeExecutionData: () => void;

  /** Whether the canvas is expanded to fill the viewport. Lives here
   * rather than in component state because two separate places need to
   * agree on it — the controls that toggle it and the canvas wrapper that
   * renders it — and because a stray DOM class survives unmount, which a
   * store value cannot. */
  isFullscreen: boolean;
  setFullscreen: (isFullscreen: boolean) => void;

  /** Whether the side inspector is open. Selecting a node deliberately
   * does **not** open it — upstream treats this as a sticky user
   * preference toggled from the node toolbar
   * (`flowStore.inspectionPanelVisible`, persisted to localStorage), and
   * a panel that appears on every click makes the canvas feel jumpy.
   * Closed by default; the toolbar's panel button toggles it. */
  isInspectorOpen: boolean;
  setInspectorOpen: (isInspectorOpen: boolean) => void;

  lastSelection: OnSelectionChangeParams | null;
  setLastSelection: (selection: OnSelectionChangeParams | null) => void;

  /** upstream's "Minimize" node-toolbar action (LE-1810: any component can
   * be minimized) — collapses a node to just its header row. Canvas-only
   * UI state, like `isInspectorOpen`: never part of `FlowNodeData`/
   * `WireFlowNode`, so collapsing a node is not something a saved flow
   * remembers. */
  minimizedNodeIds: Set<string>;
  toggleMinimized: (nodeId: string) => void;

  /** A handle the user clicked once, waiting on a second click to connect
   * (xyflow's own click-to-connect already forms the edge on that second
   * click, via its own internal `connectionClickStartHandle` — this is a
   * separate, store-owned signal purely for `TemplateNode`'s glow, so it
   * doesn't depend on subscribing to xyflow's internal store correctly
   * picking up a plain, no-drag click). Toggled: a click with nothing
   * armed arms this handle; a click with something already armed (same
   * handle, a different one, or the pane) always clears it back to null —
   * matching the natural one-click-armed / one-click-resolves rhythm,
   * without needing to know whether the second click formed a valid edge. */
  activeClickHandle: {
    nodeId: string;
    handleId: string;
    handleType: "source" | "target";
  } | null;
  setActiveClickHandle: (
    handle: {
      nodeId: string;
      handleId: string;
      handleType: "source" | "target";
    } | null
  ) => void;

  /** Shared by FlowCanvas's mod+c/mod+v hotkeys and NodeToolbar's Copy
   * button (Task 27) — kept in the store, not a component-local ref, for
   * the same reason `lastSelection` is: two call sites reading/writing
   * independent copies of "what's copied" is exactly the duplication bug
   * Task 24 found with selection tracking. */
  clipboard: PasteSelection | null;
  setClipboard: (selection: PasteSelection | null) => void;

  isDirty: boolean;
  resetDirty: () => void;

  /** Task 45: version-preview mode. While set, structural changes do NOT
   * mark the store dirty — a historical preview must never arm
   * useFlowDraft's autosave, which would otherwise overwrite the user's
   * draft with the previewed version's spec seconds later. */
  isPreviewMode: boolean;
  setPreviewMode: (isPreviewMode: boolean) => void;

  /** Task 45: replace the whole graph silently — no dirty flag, undo
   * history cleared, selection flags stripped. Used to render a historical
   * version on the canvas and to restore the working draft afterwards. */
  loadGraph: (graph: {
    nodes: CanvasNode[];
    edges: CanvasEdge[];
    viewport: Viewport;
  }) => void;

  maxHistorySize: number;
  past: HistoryEntry[];
  future: HistoryEntry[];
  takeSnapshot: () => void;
  undo: () => void;
  redo: () => void;

  paste: (selection: PasteSelection, position: PastePosition) => void;
  addNote: (position?: { x: number; y: number }) => void;
  setNodeValues: (nodeId: string, values: Record<string, unknown>) => void;
};

/** A pure-selection NodeChange/EdgeChange must not dirty the flow (Task
 * 24.8) — only structural changes (position, add, remove, dimensions, …)
 * do. xyflow fires "select" changes on every click, so this distinction is
 * the difference between "clicking a node" and "editing a node" dirtying
 * the draft. */
function hasStructuralChange(
  changes: Array<NodeChange<CanvasNode> | EdgeChange<CanvasEdge>>
): boolean {
  return changes.some((change) => change.type !== "select");
}

function snapshotOf(nodes: CanvasNode[], edges: CanvasEdge[]): HistoryEntry {
  return { nodes: cloneDeep(nodes), edges: cloneDeep(edges) };
}

function historyEntriesEqual(a: HistoryEntry, b: HistoryEntry): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** The purely-visual canvas chrome — fullscreen, inspector open/closed, the
 * current selection, minimized nodes, click-to-connect glow, clipboard. None
 * of it touches the graph, history or dirty tracking, so it lives in its own
 * slice instead of adding to the graph store's reasons to change. */
type CanvasChromeSlice = Pick<
  FlowStore,
  | "isFullscreen"
  | "setFullscreen"
  | "isInspectorOpen"
  | "setInspectorOpen"
  | "lastSelection"
  | "setLastSelection"
  | "minimizedNodeIds"
  | "toggleMinimized"
  | "activeClickHandle"
  | "setActiveClickHandle"
  | "clipboard"
  | "setClipboard"
>;

function createCanvasChromeSlice(
  set: StoreApi<FlowStore>["setState"]
): CanvasChromeSlice {
  return {
    isFullscreen: false,
    setFullscreen: (isFullscreen) => set({ isFullscreen }),

    isInspectorOpen: false,
    setInspectorOpen: (isInspectorOpen) => set({ isInspectorOpen }),

    lastSelection: null,
    setLastSelection: (selection) => set({ lastSelection: selection }),

    minimizedNodeIds: new Set(),
    toggleMinimized: (nodeId) =>
      set((state) => {
        const next = new Set(state.minimizedNodeIds);
        if (next.has(nodeId)) next.delete(nodeId);
        else next.add(nodeId);
        return { minimizedNodeIds: next };
      }),

    activeClickHandle: null,
    setActiveClickHandle: (handle) => set({ activeClickHandle: handle }),

    clipboard: null,
    setClipboard: (selection) => set({ clipboard: selection }),
  };
}

export function createFlowStore(): StoreApi<FlowStore> {
  return createStore<FlowStore>((set, get) => ({
    nodes: [],
    edges: [],

    onNodesChange: (changes) => {
      const dirties = hasStructuralChange(changes);
      set((state) => ({
        nodes: applyNodeChanges(changes, state.nodes),
        isDirty: (state.isDirty || dirties) && !state.isPreviewMode,
      }));
    },
    onEdgesChange: (changes) => {
      const dirties = hasStructuralChange(changes);
      set((state) => ({
        edges: applyEdgeChanges(changes, state.edges),
        isDirty: (state.isDirty || dirties) && !state.isPreviewMode,
      }));
    },
    setNodes: (update) => {
      const newNodes =
        typeof update === "function" ? update(get().nodes) : update;
      set((state) => ({ nodes: newNodes, isDirty: !state.isPreviewMode }));
    },
    setEdges: (update) => {
      const newEdges =
        typeof update === "function" ? update(get().edges) : update;
      set((state) => ({ edges: newEdges, isDirty: !state.isPreviewMode }));
    },

    viewport: DEFAULT_VIEWPORT,
    setViewport: (viewport) => set({ viewport }),

    nodeErrors: {},
    setNodeErrors: (nodeErrors) => set({ nodeErrors }),

    nodeRunStatus: {},
    setNodeRunStatus: (nodeRunStatus) => set({ nodeRunStatus }),
    updateNodeRunStatus: (nodeId, patch) =>
      set((state) => ({
        nodeRunStatus: {
          ...state.nodeRunStatus,
          [nodeId]: {
            status: "queued",
            startedAt: null,
            endedAt: null,
            durationMs: null,
            tokenCount: null,
            ...(state.nodeRunStatus[nodeId] ?? {}),
            ...patch,
          },
        },
      })),
    resetNodeRunStatus: () => set({ nodeRunStatus: {} }),
    nodeExecutionData: {},
    setNodeExecutionData: (nodeExecutionData) => set({ nodeExecutionData }),
    resetNodeExecutionData: () => set({ nodeExecutionData: {} }),

    ...createCanvasChromeSlice(set),

    isDirty: false,
    resetDirty: () => set({ isDirty: false }),

    isPreviewMode: false,
    setPreviewMode: (isPreviewMode) => set({ isPreviewMode }),

    loadGraph: ({ nodes, edges, viewport }) =>
      set({
        nodes: cloneDeep(nodes).map((n) => ({ ...n, selected: false })),
        edges: cloneDeep(edges).map((e) => ({ ...e, selected: false })),
        viewport,
        isDirty: false,
        past: [],
        future: [],
      }),

    maxHistorySize: MAX_HISTORY_SIZE,
    past: [],
    future: [],

    takeSnapshot: () => {
      const { nodes, edges, past, maxHistorySize } = get();
      const entry = snapshotOf(nodes, edges);
      const lastPast = past[past.length - 1];
      if (lastPast && historyEntriesEqual(lastPast, entry)) {
        return;
      }
      const trimmed =
        past.length >= maxHistorySize
          ? past.slice(past.length - maxHistorySize + 1)
          : past;
      set({ past: [...trimmed, entry], future: [] });
    },

    undo: () => {
      const { past, nodes, edges, future } = get();
      const previous = past[past.length - 1];
      if (!previous) return;
      set({
        past: past.slice(0, -1),
        future: [...future, snapshotOf(nodes, edges)],
        nodes: previous.nodes,
        edges: previous.edges,
        isDirty: true,
      });
    },

    redo: () => {
      const { future, nodes, edges, past } = get();
      const next = future[future.length - 1];
      if (!next) return;
      set({
        future: future.slice(0, -1),
        past: [...past, snapshotOf(nodes, edges)],
        nodes: next.nodes,
        edges: next.edges,
        isDirty: true,
      });
    },

    paste: (selection, position) => {
      const idsMap: Record<string, string> = {};
      let minX = Infinity;
      let minY = Infinity;
      for (const n of selection.nodes) {
        minX = Math.min(minX, n.position.x);
        minY = Math.min(minY, n.position.y);
      }
      if (!Number.isFinite(minX)) minX = 0;
      if (!Number.isFinite(minY)) minY = 0;

      const newNodes: CanvasNode[] = selection.nodes.map((original) => {
        const newId = getNodeId(original.data.type);
        idsMap[original.id] = newId;
        return {
          ...cloneDeep(original),
          id: newId,
          position: {
            x: position.x + (original.position.x - minX),
            y: position.y + (original.position.y - minY),
          },
          data: cloneDeep(original.data),
          selected: true,
        };
      });

      // Only edges whose BOTH endpoints are in the pasted selection are
      // duplicated — an edge to a node outside the selection has nothing
      // on this side of the copy to re-point it to.
      const newEdges: CanvasEdge[] = [];
      for (const edge of selection.edges) {
        const source = idsMap[edge.source];
        const target = idsMap[edge.target];
        if (!source || !target) continue;
        newEdges.push({
          ...cloneDeep(edge),
          id: getNodeId("edge"),
          source,
          target,
          selected: false,
        });
      }

      set((state) => ({
        nodes: [
          ...state.nodes.map((n) => ({ ...n, selected: false })),
          ...newNodes,
        ],
        edges: [
          ...state.edges.map((e) => ({ ...e, selected: false })),
          ...newEdges,
        ],
        isDirty: true,
      }));
    },

    addNote: (position) => {
      const { nodes, takeSnapshot } = get();
      takeSnapshot();
      const newId = getNodeId(NOTE_COMPONENT_TYPE);
      const pos = position ?? {
        x: NOTE_DROP_ORIGIN + Math.random() * NOTE_DROP_JITTER,
        y: NOTE_DROP_ORIGIN + Math.random() * NOTE_DROP_JITTER,
      };
      const newNode: CanvasNode = {
        id: newId,
        type: RendererNodeType.Note,
        position: pos,
        data: {
          type: NOTE_COMPONENT_TYPE,
          templateVersion: 1,
          values: {
            text: "",
            color: "yellow",
          },
        },
        selected: true,
      };
      set({
        nodes: [...nodes.map((n) => ({ ...n, selected: false })), newNode],
        isDirty: true,
      });
    },

    setNodeValues: (nodeId, values) =>
      set((state) => ({
        nodes: state.nodes.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  values: { ...(n.data?.values ?? {}), ...values },
                },
              }
            : n
        ),
        isDirty: true,
      })),
  }));
}
