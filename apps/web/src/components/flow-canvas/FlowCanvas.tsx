/**
 * Ported from Langflow (MIT) — src/frontend/src/pages/FlowPage/components/PageComponent/index.tsx
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx: this is the canvas shell — the single highest-value
 * port in P4. See .tmp/flow-canvas-task-20-report.md and
 * .tmp/flow-canvas-port-triage.md for what was and wasn't carried over;
 * the short version is that everything Langflow-vertex-build/run-specific
 * was dropped or rewired (Task 28), while the pure interaction layer
 * (helper lines, drag-select fix, copy/paste/undo/redo, delete-with-
 * snapshot, connection legality, the ReactFlow prop tuning) is preserved.
 *
 * `nodeTypes` is optional and defaults to xyflow's own generic node
 * renderer — Task 26 supplies the real `TemplateNode`. This keeps the
 * canvas shell testable and usable before that task lands, rather than
 * this task blocking on it.
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

"use client";

import {
  Background,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type ConnectionLineComponent,
  type EdgeTypes,
  type NodeTypes,
  type OnSelectionChangeParams,
  type XYPosition,
} from "@xyflow/react";
import { cloneDeep } from "lodash";
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { cn } from "@/lib/utils";
import { useHotkeys } from "react-hotkeys-hook";
import { useStore, type StoreApi } from "zustand";
import { useTheme } from "next-themes";
import "@xyflow/react/dist/style.css";
// Langflow's own design tokens + xyflow surface overrides, scoped to
// `.langflow-canvas`. Imported after xyflow's stylesheet so the surface
// rules win. See the file header for why this exists.
import "./langflow-theme.css";

import { CanvasControls } from "./components/CanvasControls";
import { DefaultEdge } from "./edges/DefaultEdge";
import { getHelperLines, type HelperLinesState } from "./helpers/helperLines";
import { useCanvasDragSelectFix } from "./hooks/useCanvasDragSelectFix";
import { useMousePosition } from "./hooks/useMousePosition";
import type { FlowStore } from "./stores/flowStore";
import type { CanvasEdge, CanvasNode, PortType } from "./types/flow";
import { isEditableTarget } from "./utils/isEditableTarget";
import { isValidConnection } from "./utils/isValidConnection";
import { isFlowJsonFile, useFlowImport } from "./hooks/useFlowImport";
import { useTranslation } from "react-i18next";
import { SvgUploadCloud } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 2;
// After an import replaces the graph, wait one paint for the new nodes to
// mount, then animate the viewport to fit them.
const FIT_VIEW_DEFER_MS = 50;
const FIT_VIEW_ANIM_MS = 200;

export type HandleTypeLookup = (
  nodeId: string,
  handleName: string,
  direction: "source" | "target"
) => PortType[] | null;

export type FlowCanvasProps = {
  store: StoreApi<FlowStore>;
  lookupHandleTypes: HandleTypeLookup;
  nodeTypes?: NodeTypes;
  /** Task 25's sidebar sets `event.dataTransfer` with the dragged
   * component's type; this resolves the drop into a new node at the
   * correct canvas position. Omit while Task 25 doesn't exist yet. */
  onDropComponentType?: (componentType: string, position: XYPosition) => void;
  readOnly?: boolean;
  /** The editor always wants the minimap; a small embedded preview (e.g.
   * the chat timeline's flow-stage card) doesn't have room for one. */
  showMinimap?: boolean;
  /** Renders controls and minimap in a compact form factor for previews/modals. */
  compact?: boolean;
  /** upstream PageComponent passes `connectionLineComponent` so the
   * drag-in-progress line is Langflow's, not xyflow's default. Optional
   * here because it needs the template registry to colour itself. */
  connectionLineComponent?: ConnectionLineComponent<CanvasNode>;
};

/** vendor/langflow/pages/FlowPage/components/PageComponent/MemoizedComponents.tsx:15
 * — `<Background id="main-canvas-bg" size={2} gap={20} />`, verbatim. The
 * dot size/spacing pair is what gives the canvas its Langflow texture.
 *
 * `color` is passed explicitly rather than styled through CSS: xyflow
 * generates the `<pattern>` internally and an earlier attempt to reach it
 * with a selector silently stopped matching. `currentColor` lets the
 * `text-canvas-dot` class on the wrapper decide the shade, so the dots
 * still follow the light/dark token. */
const MemoizedBackground = memo(() => (
  <Background
    id="main-canvas-bg"
    size={2}
    gap={20}
    color="currentColor"
    className="text-canvas-dot"
  />
));
MemoizedBackground.displayName = "MemoizedBackground";

/** vendor/langflow/pages/FlowPage/consts.ts:14 — `{ default: DefaultEdge }`.
 * Registering it under `default` means every edge picks it up without each
 * one having to name a type, which is how upstream does it too. */
const EDGE_TYPES: EdgeTypes = { default: DefaultEdge };

const MemoizedMiniMap = memo(({ compact = false }: { compact?: boolean }) => (
  <MiniMap
    pannable
    zoomable
    style={
      compact
        ? {
            width: 75,
            height: 48,
          }
        : undefined
    }
    nodeBorderRadius={compact ? 2 : 4}
    className={cn(
      "!m-0",
      compact
        ? "!bottom-2 !right-2 !rounded-md shadow-xs"
        : "!bottom-4 !right-4 !rounded-lg shadow-md"
    )}
  />
));
MemoizedMiniMap.displayName = "MemoizedMiniMap";

function HelperLinesOverlay({ lines }: { lines: HelperLinesState }) {
  return (
    <svg className="pointer-events-none absolute inset-0 h-full w-full">
      {lines.horizontal && (
        <line
          x1={0}
          y1={lines.horizontal.position}
          x2="100%"
          y2={lines.horizontal.position}
          className="stroke-theme-primary-05"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      )}
      {lines.vertical && (
        <line
          x1={lines.vertical.position}
          y1={0}
          x2={lines.vertical.position}
          y2="100%"
          className="stroke-theme-primary-05"
          strokeWidth={1}
          strokeDasharray="4 2"
        />
      )}
    </svg>
  );
}

function FlowCanvasInner({
  store,
  lookupHandleTypes,
  nodeTypes,
  onDropComponentType,
  readOnly = false,
  showMinimap = true,
  compact = false,
  connectionLineComponent,
}: FlowCanvasProps) {
  const { t } = useTranslation();
  const nodes = useStore(store, (s) => s.nodes);
  const edges = useStore(store, (s) => s.edges);
  const onNodesChange = useStore(store, (s) => s.onNodesChange);
  const onEdgesChange = useStore(store, (s) => s.onEdgesChange);
  const setNodes = useStore(store, (s) => s.setNodes);
  const setEdges = useStore(store, (s) => s.setEdges);
  // The store's lastSelection is the single source of truth — Task 27's
  // NodeInspector reads the same field, so selection state must never be
  // shadowed by a component-local copy that only this component's own
  // handlers see.
  const lastSelection = useStore(store, (s) => s.lastSelection);
  const setLastSelection = useStore(store, (s) => s.setLastSelection);
  const takeSnapshot = useStore(store, (s) => s.takeSnapshot);
  const undo = useStore(store, (s) => s.undo);
  const redo = useStore(store, (s) => s.redo);
  const paste = useStore(store, (s) => s.paste);
  // Store-backed, not a component-local ref — Task 27's NodeToolbar Copy
  // button writes/reads the same field, so a canvas Ctrl+C followed by a
  // toolbar Paste (or vice versa) sees one consistent clipboard.
  const clipboard = useStore(store, (s) => s.clipboard);
  const setClipboard = useStore(store, (s) => s.setClipboard);
  const setViewport = useStore(store, (s) => s.setViewport);
  const isFullscreen = useStore(store, (s) => s.isFullscreen);
  const setFullscreen = useStore(store, (s) => s.setFullscreen);
  const toggleMinimized = useStore(store, (s) => s.toggleMinimized);
  const setActiveClickHandle = useStore(store, (s) => s.setActiveClickHandle);
  const addNote = useStore(store, (s) => s.addNote);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const mousePosition = useMousePosition(wrapperRef);
  const reactFlowInstance = useReactFlow();
  const { resolvedTheme } = useTheme();
  const [helperLines, setHelperLines] = useState<HelperLinesState>({});
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const dragCounterRef = useRef(0);

  const fitViewAfterImport = useCallback(() => {
    setTimeout(() => {
      reactFlowInstance.fitView({
        duration: FIT_VIEW_ANIM_MS,
        minZoom: MIN_ZOOM,
        maxZoom: MAX_ZOOM,
      });
    }, FIT_VIEW_DEFER_MS);
  }, [reactFlowInstance]);
  const { importFromFile } = useFlowImport(store, fitViewAfterImport);

  useCanvasDragSelectFix(wrapperRef);

  const handleSelectionChange = useCallback(
    (selection: OnSelectionChangeParams) => {
      setLastSelection(selection);
    },
    [setLastSelection]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      const ok = isValidConnection(connection, edges, lookupHandleTypes);
      if (!ok) return; // §10 — rejected client-side, no request issued
      takeSnapshot();
      setEdges((current) => [
        ...current,
        {
          id: `${connection.source}-${connection.sourceHandle}-${connection.target}-${connection.targetHandle}`,
          source: connection.source!,
          target: connection.target!,
          sourceHandle: connection.sourceHandle,
          targetHandle: connection.targetHandle,
        },
      ]);
    },
    [readOnly, edges, lookupHandleTypes, takeSnapshot, setEdges]
  );

  // Clears a click-armed handle (TemplateNode's `activeClickHandle`,
  // NodeHandle.tsx's click-to-glow) when the user clicks empty canvas
  // instead of a second handle — otherwise a changed-my-mind click leaves
  // the glow stuck on until some other handle is eventually clicked.
  const handlePaneClick = useCallback(() => {
    setActiveClickHandle(null);
  }, [setActiveClickHandle]);

  const handleNodeClick = useCallback(
    (_event: ReactMouseEvent, _node: CanvasNode) => {
      // In readOnly mode, passing this handler to ReactFlow ensures xyflow sets hasPointerEvents=true,
      // allowing interactive elements inside nodes (e.g. execution drawers) to receive clicks.
    },
    []
  );

  const handleNodeDrag = useCallback(
    (_event: unknown, draggedNode: CanvasNode) => {
      setHelperLines(getHelperLines(draggedNode, nodes));
    },
    [nodes]
  );

  const clearHelperLines = useCallback(() => setHelperLines({}), []);

  // deleteKeyCode={[]} disables xyflow's own delete so this handler can
  // takeSnapshot() *before* removing — the reason delete is undoable.
  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent) => {
      if (readOnly) return;
      if (isEditableTarget(event.target)) return;

      const isUndo =
        (event.metaKey || event.ctrlKey) &&
        event.key === "z" &&
        !event.shiftKey;
      const isRedo =
        ((event.metaKey || event.ctrlKey) && event.key === "y") ||
        ((event.metaKey || event.ctrlKey) &&
          event.shiftKey &&
          event.key === "z");
      if (isUndo) {
        event.preventDefault();
        undo();
        return;
      }
      if (isRedo) {
        event.preventDefault();
        redo();
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
        if (!lastSelection || !lastSelection.nodes.length) return;
        event.preventDefault();
        const selectedNodes = lastSelection.nodes as CanvasNode[];
        const selectedEdges = lastSelection.edges;
        const anchor = selectedNodes[0];
        if (!anchor) return;
        takeSnapshot();
        paste(
          { nodes: selectedNodes, edges: selectedEdges },
          { x: anchor.position.x + 40, y: anchor.position.y + 40 }
        );
        return;
      }

      if (
        event.key.toLowerCase() === "m" &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        if (!lastSelection || !lastSelection.nodes.length) return;
        event.preventDefault();
        for (const node of lastSelection.nodes) {
          toggleMinimized(node.id);
        }
        return;
      }

      if (event.key === "Delete" || event.key === "Backspace") {
        if (
          !lastSelection ||
          (!lastSelection.nodes.length && !lastSelection.edges.length)
        ) {
          return;
        }
        event.preventDefault();
        takeSnapshot();
        const nodeIds = new Set(lastSelection.nodes.map((n) => n.id));
        const edgeIds = new Set(lastSelection.edges.map((e) => e.id));
        setNodes((current) => current.filter((n) => !nodeIds.has(n.id)));
        setEdges((current) =>
          current.filter(
            (e) =>
              !edgeIds.has(e.id) &&
              !nodeIds.has(e.source) &&
              !nodeIds.has(e.target)
          )
        );
      }
    },
    [readOnly, undo, redo, takeSnapshot, setNodes, setEdges, lastSelection]
  );

  useHotkeys(
    "mod+c",
    () => {
      if (readOnly) return;
      if (
        lastSelection &&
        (lastSelection.nodes.length || lastSelection.edges.length)
      ) {
        setClipboard(
          cloneDeep({
            nodes: lastSelection.nodes as CanvasNode[],
            edges: lastSelection.edges,
          })
        );
      }
    },
    { enableOnFormTags: false }
  );

  useHotkeys(
    "mod+v",
    () => {
      if (readOnly) return;
      if (!clipboard) return;
      takeSnapshot();
      paste(clipboard, mousePosition.current);
    },
    { enableOnFormTags: false }
  );

  useHotkeys(
    "mod+d",
    (e) => {
      if (readOnly) return;
      e.preventDefault();
      const selectedNodes = nodes.filter((n) => n.selected);
      if (selectedNodes.length === 0) return;
      // Snapshot before pasting so duplication is its own history entry —
      // without this, undo falls back to whatever snapshot preceded it
      // (e.g. a drag's pre-move state) and reverts both at once.
      takeSnapshot();
      paste({ nodes: selectedNodes, edges: [] }, mousePosition.current);
    },
    { enableOnFormTags: false }
  );

  const handleDragEnter = useCallback((event: React.DragEvent) => {
    if (event.dataTransfer.types.includes("Files")) {
      event.preventDefault();
      dragCounterRef.current += 1;
      setIsDraggingFile(true);
    }
  }, []);

  const handleDragLeave = useCallback((event: React.DragEvent) => {
    if (event.dataTransfer.types.includes("Files")) {
      event.preventDefault();
      dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
      if (dragCounterRef.current === 0) {
        setIsDraggingFile(false);
      }
    }
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      dragCounterRef.current = 0;
      setIsDraggingFile(false);
      if (readOnly) return;

      // 1. Check if a JSON file was dropped
      const file = event.dataTransfer.files?.[0];
      if (file && isFlowJsonFile(file)) {
        importFromFile(file);
        return;
      }

      // 2. Otherwise handle component drop from sidebar
      if (!onDropComponentType) return;
      const componentType =
        event.dataTransfer.getData("application/x-flow-component-type") ||
        event.dataTransfer.getData("text/plain");
      if (!componentType) return;
      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      onDropComponentType(componentType, position);
    },
    [readOnly, onDropComponentType, reactFlowInstance, importFromFile]
  );

  const handleDragOver = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer.types.includes("Files")) {
        event.dataTransfer.dropEffect = "copy";
        if (!isDraggingFile) {
          setIsDraggingFile(true);
        }
      } else {
        event.dataTransfer.dropEffect = "move";
      }
    },
    [isDraggingFile]
  );

  const fitViewOptions = useMemo(
    () => ({ minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM }),
    []
  );

  const toggleFullscreen = useCallback(
    () => setFullscreen(!isFullscreen),
    [isFullscreen, setFullscreen]
  );

  const handleAddNote = useCallback(() => {
    if (readOnly) return;
    const centerPos = reactFlowInstance.screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 2,
    });
    addNote(centerPos);
  }, [readOnly, reactFlowInstance, addNote]);

  // Expanding is `FlowEditorShell`'s job — it owns the element that grows,
  // the Escape handler and the scroll lock, because the palette and
  // inspector have to come along and a portal is needed to escape the app
  // shell's container context. What's left here is the consequence:
  // xyflow measures its container once, so a resize needs a refit or the
  // graph stays anchored to the old bounds.
  useEffect(() => {
    const timer = window.setTimeout(
      () => reactFlowInstance.fitView({ duration: 200, ...fitViewOptions }),
      260 // past the shell's 200ms transition, so it settles at final size
    );
    return () => window.clearTimeout(timer);
  }, [isFullscreen, reactFlowInstance, fitViewOptions]);

  // Initial framing is done here, not by xyflow's `fitView` prop. That prop
  // sets `fitViewQueued`, which xyflow's ResizeObserver path resolves on the
  // *first* node it measures — so an async-loaded graph (useFlowDraft's
  // fetch, FlowAgentPreview's SWR call) gets framed around one half-mounted
  // node, then reframed once the rest arrive: a visible double-fit on every
  // page load. Instead we hold off and fit exactly once, when
  // `useNodesInitialized` reports every node has real measured dimensions
  // (TemplateNode mounts each as a zero-size, handle-less skeleton until its
  // template resolves). `duration: 0` so the first frame lands without an
  // animated pan across the canvas from the origin.
  const nodesInitialized = useNodesInitialized();
  const hasFitLoadedGraphRef = useRef(false);
  useEffect(() => {
    if (
      hasFitLoadedGraphRef.current ||
      nodes.length === 0 ||
      !nodesInitialized
    ) {
      return;
    }
    hasFitLoadedGraphRef.current = true;
    reactFlowInstance.fitView({ duration: 0, ...fitViewOptions });
  }, [nodes.length, nodesInitialized, reactFlowInstance, fitViewOptions]);

  return (
    <div
      ref={wrapperRef}
      className="langflow-canvas relative h-full w-full bg-canvas"
      onKeyDown={handleKeyDown}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      data-testid="flow-canvas-wrapper"
    >
      {/* Explicit generics, as upstream does (`<ReactFlow<AllNodeType, EdgeType>`,
          PageComponent/index.tsx:925) — passing `edgeTypes` otherwise makes
          inference fall back to the base `Node`/`Edge` and every handler
          below stops type-checking against `CanvasNode`. */}
      <ReactFlow<CanvasNode, CanvasEdge>
        nodes={nodes}
        edges={edges}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        className={cn(
          readOnly &&
            "[&_.react-flow__node]:!pointer-events-auto [&_.react-flow__node]:select-none"
        )}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={EDGE_TYPES}
        connectionLineComponent={connectionLineComponent}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onPaneClick={handlePaneClick}
        onNodeDrag={handleNodeDrag}
        onNodeDragStop={clearHelperLines}
        onSelectionChange={handleSelectionChange}
        onMoveEnd={(_event, viewport) => setViewport(viewport)}
        isValidConnection={(conn) =>
          isValidConnection(conn as Connection, edges, lookupHandleTypes)
        }
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        // Hard-won interaction tuning, ported verbatim from Langflow rather
        // than re-derived — see task-24-report.md.
        connectionRadius={30}
        onlyRenderVisibleElements={true}
        selectNodesOnDrag={false}
        elevateEdgesOnSelect={false}
        disableKeyboardA11y={true}
        deleteKeyCode={[]}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        zoomOnScroll={true}
        zoomOnPinch={true}
        panOnDrag={true}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
      >
        <MemoizedBackground />
        <CanvasControls
          isFullscreen={isFullscreen}
          onToggleFullscreen={toggleFullscreen}
          onAddNote={readOnly ? undefined : handleAddNote}
          compact={compact}
        />
        {showMinimap && <MemoizedMiniMap compact={compact} />}
      </ReactFlow>
      <HelperLinesOverlay lines={helperLines} />
      {isDraggingFile && (
        <div
          className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center bg-background-neutral-00/60 backdrop-blur-xs transition-all duration-200 p-6"
          data-testid="flow-canvas-drop-overlay"
        >
          <div className="flex flex-col items-center justify-center gap-3 w-full h-full max-w-md max-h-64 rounded-2xl border-2 border-dashed border-primary bg-background-neutral-00 shadow-2xl p-8 text-center animate-pulse">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary shadow-sm">
              <SvgUploadCloud className="h-8 w-8 animate-bounce stroke-current" />
            </div>
            <div className="flex flex-col gap-1">
              <Text as="h3" className="text-base font-semibold text-text-05">
                {t("flowCanvas.dropJsonHere", "Drop the JSON flow file here")}
              </Text>
              <Text as="p" className="text-xs text-text-03">
                {t(
                  "flowCanvas.dropJsonDescription",
                  "Drop it to load your flow onto the canvas"
                )}
              </Text>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
