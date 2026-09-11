"use client";

/**
 * Ported from Langflow (MIT) — vendor/langflow/CustomNodes/GenericNode/index.tsx
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * The card layout and its Tailwind classes are upstream's, carried over
 * verbatim rather than reinterpreted (upstream :560-700):
 *
 *   w-80 · rounded-xl border shadow-sm hover:shadow-md   (the card)
 *   px-4 py-3 · border-b                                 (the header)
 *   px-4 pb-3                                            (the description)
 *
 * Langflow's classNames resolve here because `tailwind.config.js` aliases
 * shadcn's semantic tokens (`muted`, `accent`, `card`, `ring`, …) onto
 * this project's CSS variables — see the block there. The design is
 * Langflow's; only the module specifiers and the data source differ.
 *
 * Why not import upstream directly: `vendor/langflow` is a reference copy
 * of seven subtrees, not a self-contained package. `GenericNode` alone
 * imports seven `@/…` paths of which one exists in the copy, and the
 * transitive closure reaches `react-router-dom` and `@tanstack/react-query`
 * — a Vite SPA's router and data layer, which a Next.js App Router build
 * cannot host. The `vendorBoundary` test (Task 20) enforces that boundary.
 *
 * Data-shape divergence (unchanged from Task 26): Langflow reads field
 * descriptors from `node.data.node.template` — the template is embedded in
 * the node. Ours looks the `ComponentTemplate` up from the registry by
 * `node.data.type`, because P1 stores values only (R1, design spec §4.4).
 *
 * Dropped from GenericNode's 18 sub-components (full reasoning in
 * task-26-report.md): `NodeUpdateComponent`/`NodeLegacyComponent`,
 * `NodeStatus`/`use-get-build-status` (P7 Task 45 covers run status),
 * `NodeDialogComponent`/`outputModal`, `NodeName` (inline rename — no
 * field exists to persist it to), `HumanInputNodeBadge`.
 */

import { useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  useConnection,
  useStore as useXyStore,
  useUpdateNodeInternals,
  type NodeProps,
} from "@xyflow/react";
import { useStore, type StoreApi } from "zustand";
import { cn } from "@/lib/utils";

import { NodeFieldList } from "../components/NodeFieldList";
import { NodeStatusBadge } from "../components/NodeStatusBadge";
import { NodeToolbar } from "../components/NodeToolbar";
import { NodeExecutionDrawer } from "./NodeExecutionDrawer";
import { useComponentTemplates } from "../hooks/useComponentTemplates";
import { expandAgentIntoFlow } from "../utils/expandAgentIntoFlow";
import type { FlowStore } from "../stores/flowStore";

import Text from "@/refresh-components/texts/Text";
import type { CanvasNode, PortType, ValidationIssue } from "../types/flow";
import { findTemplateByType } from "../utils/findTemplate";
import { handlesCompatible } from "../utils/handleTypes";
import {
  getEffectiveInputHandles,
  getEffectiveOutputHandles,
} from "../utils/templateSchema";

const NO_ERRORS: ValidationIssue[] = [];

import {
  NodeCard,
  NodeHeader,
  NodeDescription,
  HandleRow,
} from "./templateNodeParts";

export function createTemplateNode(
  store: StoreApi<FlowStore>,
  readOnly: boolean = false
) {
  return function TemplateNode({ id, data, selected }: NodeProps<CanvasNode>) {
    const { t } = useTranslation();
    const { data: grouped, isLoading } = useComponentTemplates();
    const setNodes = useStore(store, (s) => s.setNodes);
    const nodeErrors = useStore(store, (s) => s.nodeErrors[id] ?? NO_ERRORS);
    const runStatus = useStore(store, (s) => s.nodeRunStatus[id]);
    const executionData = useStore(
      store,
      (s) =>
        s.nodeExecutionData?.[id] ||
        (typeof data.values?.stage_name === "string"
          ? s.nodeExecutionData?.[data.values.stage_name.toLowerCase()]
          : undefined) ||
        (typeof data.type === "string"
          ? s.nodeExecutionData?.[data.type.toLowerCase()]
          : undefined)
    );
    // upstream's "Minimize" toolbar action (LE-1810) — collapses the card
    // to just its header. Handle rows stay mounted (not conditionally
    // removed) so xyflow keeps tracking their real DOM position for
    // existing edges; only their containing row collapses to zero height.
    const isMinimized = useStore(store, (s) => s.minimizedNodeIds.has(id));
    // upstream's "glow every handle you can connect to while dragging"
    // (handleRenderComponent's `openHandle`). xyflow tracks a connection
    // in progress two separate ways — `state.connection` for an actual
    // pointer drag, `state.connectionClickStartHandle` for connectOnClick
    // (the default: click one handle, then click another, no drag needed)
    // — and only the drag one is exposed by the public `useConnection`
    // hook. Missing the click path here was the actual bug (a real click
    // never sets `state.connection`), found by asking whether hover-glow
    // — unrelated to this task, pre-existing, and unaffected by either
    // path — worked at all; it didn't, which is what pointed at
    // `connectionClickStartHandle` rather than a mistake in the
    // compatibility math itself. `connectionClickStartHandle` isn't
    // covered by any dedicated public hook, so it's read via `useStore`
    // (from `@xyflow/react`, aliased to avoid the zustand import above) —
    // the same public escape hatch xyflow's own docs point to for
    // internal-state slices with no dedicated hook.
    const dragConnection = useConnection((c) => ({
      inProgress: c.inProgress,
      fromNodeId: c.fromNode?.id,
      fromHandleType: c.fromHandle?.type,
      fromHandleId: c.fromHandle?.id,
      fromComponentType: (c.fromNode?.data as { type?: string } | undefined)
        ?.type,
      fromComponentValues: (
        c.fromNode?.data as { values?: Record<string, unknown> } | undefined
      )?.values,
    }));
    const clickStartHandle = useXyStore((s) => s.connectionClickStartHandle);
    // A plain click (no drag) doesn't reliably surface through xyflow's
    // `connectionClickStartHandle` for glow purposes here — its pointer
    // machinery is gated by `connectionDragThreshold` (a stationary
    // press-release never crosses it, so `state.connection` never updates),
    // and relying on the native `click` event's own store write turned out
    // not to reach every other node's glow reliably either. This is a
    // separate, store-owned "armed by one click" signal instead — purely
    // additive, doesn't touch xyflow's own click-to-connect edge-forming
    // logic (still entirely xyflow's, still works off its own state).
    const activeClickHandle = useStore(store, (s) => s.activeClickHandle);
    const setActiveClickHandle = useStore(store, (s) => s.setActiveClickHandle);
    const handleClickToggle = useCallback(
      (handleId: string, handleType: "source" | "target") => {
        setActiveClickHandle(
          store.getState().activeClickHandle
            ? null
            : { nodeId: id, handleId, handleType }
        );
      },
      [id, store, setActiveClickHandle]
    );

    // Unifies all three sources above into one origin, resolving its declared
    // PortTypes via the same Router-aware `getEffectiveOutputHandles` this
    // node's own outputs use below. `handleType` here is whichever side
    // the user actually grabbed — xyflow allows starting from either a
    // source or a target handle, so this glows source handles when the
    // drag started from a target one, not just the more common direction.
    const dragOrigin = useMemo((): {
      nodeId: string;
      handleType: "source" | "target";
      types: PortType[] | null;
    } | null => {
      let nodeId: string | undefined;
      let handleId: string | null | undefined;
      let handleType: "source" | "target" | undefined;
      let componentType: string | undefined;
      let componentValues: Record<string, unknown> | undefined;

      if (dragConnection.inProgress) {
        nodeId = dragConnection.fromNodeId;
        handleId = dragConnection.fromHandleId;
        handleType = dragConnection.fromHandleType;
        componentType = dragConnection.fromComponentType;
        componentValues = dragConnection.fromComponentValues;
      } else if (activeClickHandle) {
        nodeId = activeClickHandle.nodeId;
        handleId = activeClickHandle.handleId;
        handleType = activeClickHandle.handleType;
        const originNode = store.getState().nodes.find((n) => n.id === nodeId);
        componentType = originNode?.data.type;
        componentValues = originNode?.data.values;
      } else if (clickStartHandle) {
        nodeId = clickStartHandle.nodeId;
        handleId = clickStartHandle.id;
        handleType = clickStartHandle.type;
        const originNode = store.getState().nodes.find((n) => n.id === nodeId);
        componentType = originNode?.data.type;
        componentValues = originNode?.data.values;
      }

      if (!nodeId || !handleId || !handleType || !componentType || !grouped)
        return null;
      const originTemplate = findTemplateByType(grouped, componentType);
      if (!originTemplate) return null;
      const originHandles =
        handleType === "source"
          ? getEffectiveOutputHandles(originTemplate, componentValues ?? {})
          : originTemplate.handles.inputs;
      // Handle.types mirrors the backend's PortType-valued list as plain
      // strings (types/componentTemplate.ts) — trusted, not re-validated,
      // same as useHandleTypeLookup's identical cast in useCanvasWiring.ts.
      const types =
        (originHandles.find((h) => h.name === handleId)?.types as
          | PortType[]
          | undefined) ?? null;
      return { nodeId, handleType, types };
    }, [
      dragConnection.inProgress,
      dragConnection.fromNodeId,
      dragConnection.fromHandleType,
      dragConnection.fromHandleId,
      dragConnection.fromComponentType,
      dragConnection.fromComponentValues,
      activeClickHandle,
      clickStartHandle,
      grouped,
      store,
    ]);
    const isDragOriginNode = dragOrigin?.nodeId === id;

    // Which of this node's target handles already have an edge — drives
    // the port rows' "Receiving …" state, matching upstream's locked box.
    const edges = useStore(store, (s) => s.edges);
    const connectedTargets = useMemo(
      () =>
        new Set(
          edges
            .filter((e) => e.target === id && e.targetHandle)
            .map((e) => e.targetHandle as string)
        ),
      [edges, id]
    );

    const updateValue = useCallback(
      (key: string, value: unknown) => {
        setNodes((current) =>
          current.map((n) =>
            n.id === id
              ? {
                  ...n,
                  data: {
                    ...n.data,
                    values: { ...n.data.values, [key]: value },
                  },
                }
              : n
          )
        );
      },
      [id, setNodes]
    );

    // Rules-of-Hooks: these must run on every render, before either early
    // return below — `isLoading`/`!template` genuinely flip mid-lifetime
    // (useComponentTemplates' fetch resolves after the node has already
    // mounted once), and hooks declared only past a conditional return
    // change count between that node's own renders, which React treats as
    // a hard error and unmounts the tree above the nearest boundary. That
    // silently blanked the whole canvas the moment templates finished
    // loading — no visible error, just nothing on screen.
    const takeSnapshot = useStore(store, (s) => s.takeSnapshot);
    const updateNodeRunStatus = useStore(store, (s) => s.updateNodeRunStatus);
    const updateDescription = useCallback(
      (newDesc: string) => {
        takeSnapshot();
        setNodes((current) =>
          current.map((n) =>
            n.id === id
              ? { ...n, data: { ...n.data, description: newDesc } }
              : n
          )
        );
      },
      [id, setNodes, takeSnapshot]
    );

    const handleRunNode = useCallback(() => {
      takeSnapshot();
      const startTime = Date.now();
      updateNodeRunStatus(id, {
        status: "running",
        startedAt: startTime,
        endedAt: null,
        durationMs: null,
      });

      setTimeout(() => {
        const endTime = Date.now();
        updateNodeRunStatus(id, {
          status: "done",
          startedAt: startTime,
          endedAt: endTime,
          durationMs: endTime - startTime,
        });
      }, 1000);
    }, [id, takeSnapshot, updateNodeRunStatus]);

    const handleExpandAgent = useCallback(() => {
      const agentId = (data.values as { agent_id?: string } | undefined)
        ?.agent_id;
      if (!agentId) return;
      const selfNode = store.getState().nodes.find((n) => n.id === id);
      const position = selfNode
        ? { x: selfNode.position.x + 280, y: selfNode.position.y }
        : { x: 0, y: 0 };
      void expandAgentIntoFlow(agentId, store, position);
    }, [data.values, id, store]);

    // xyflow measures a node's handle anchor points once (on mount) and then
    // only on a drag/resize. This node mounts as a handle-less skeleton
    // while `useComponentTemplates` is still loading, then swaps in the real
    // node with its input/output ports — and a Router/Loop node's effective
    // output handles further change with its own values. Without an explicit
    // nudge xyflow keeps the stale (or absent) bounds, so the output port
    // renders detached from its row and existing edges anchor to the wrong
    // spot until the node is dragged. Mirrors Langflow's own GenericNode
    // effect keyed on `data.node.template`
    // (vendor/langflow/CustomNodes/GenericNode/index.tsx).
    const updateNodeInternals = useUpdateNodeInternals();
    const resolvedTemplate = useMemo(
      () => (grouped ? findTemplateByType(grouped, data.type) : undefined),
      [grouped, data.type]
    );
    const handleAnchorKey = useMemo(() => {
      if (!resolvedTemplate) return "";
      const inputs = resolvedTemplate.handles.inputs
        .map((h) => h.name)
        .join(",");
      const outputs = getEffectiveOutputHandles(resolvedTemplate, data.values)
        .map((h) => h.name)
        .join(",");
      return `${inputs}|${outputs}`;
    }, [resolvedTemplate, data.values]);
    useEffect(() => {
      if (!resolvedTemplate) return;
      updateNodeInternals(id);
    }, [id, resolvedTemplate, handleAnchorKey, updateNodeInternals]);

    if (isLoading) {
      return (
        <NodeCard selected={selected} testId={`template-node-loading-${id}`}>
          <div className="m-4 h-16 animate-pulse rounded-lg bg-muted" />
        </NodeCard>
      );
    }

    const template = resolvedTemplate;
    const displayName = template
      ? t(`flowCanvas.components.${data.type}.name`, template.display_name)
      : data.type;

    if (!template) {
      return (
        <NodeCard selected={selected} testId={`template-node-unknown-${id}`}>
          <div className="px-4 py-3">
            <span className="text-sm font-medium text-canvas-fg">
              {t(
                "flowCanvas.inspector.unknownComponent",
                "Unknown component: {{type}}",
                { type: data.type }
              )}
            </span>
            <Text as="p" className="mt-1 text-sm text-muted-foreground">
              {t(
                "flowCanvas.inspector.unknownComponentDesc",
                "This component isn't registered. Its saved values are kept, not lost."
              )}
            </Text>
          </div>
        </NodeCard>
      );
    }

    const customDescription = data.description;
    const defaultDescription = template?.description
      ? t(
          `flowCanvas.components.${data.type}.description`,
          template.description
        )
      : "";
    const nodeDescription =
      customDescription !== undefined ? customDescription : defaultDescription;

    const outputHandles = getEffectiveOutputHandles(template, data.values);
    const inputHandles = getEffectiveInputHandles(template, data.values);
    // A port's inline field is its own name's field, or the one it declares
    // as `fallback_field` — Langflow's MessageInput shape: the row shows an
    // editable value until an edge lands on it, then "Receiving X".
    const handleFieldKey = (h: (typeof inputHandles)[number]) =>
      template.inputs[h.name] ? h.name : h.fallback_field ?? undefined;
    const hasFields = Object.keys(template.inputs).length > 0;
    // Upstream renders "Use as agent tool" as a toolbar action, not a card
    // field (nodeToolbarComponent/index.tsx:527-583) — kept out of
    // NodeFieldList below so it doesn't also show up as a plain checkbox row.
    const toolModeKey = template.tool_mode_field ?? undefined;
    const toolModeValue = toolModeKey
      ? Boolean(data.values[toolModeKey])
      : false;

    return (
      <NodeCard
        selected={!readOnly && selected}
        hasErrors={nodeErrors.length > 0}
        readOnly={readOnly}
        runStatus={runStatus}
        testId={`template-node-${id}`}
      >
        {!readOnly && selected && (
          <NodeToolbar
            nodeId={id}
            store={store}
            hasParameters={hasFields}
            hasToolMode={!!toolModeKey}
            toolModeValue={toolModeValue}
            onToolModeChange={
              toolModeKey ? (v) => updateValue(toolModeKey, v) : undefined
            }
          />
        )}

        {/* upstream :601-604 — header block, `border-b` closes it. When
            minimized there's nothing below to close off, matching
            upstream's own minimized header (no divider, no description). */}
        <div className={cn("grid leading-5", !isMinimized && "border-b")}>
          <div className="flex items-center justify-between pr-3">
            <NodeHeader
              icon={template.icon}
              title={displayName}
              errors={nodeErrors}
              onRun={readOnly ? undefined : handleRunNode}
              isRunning={runStatus?.status === "running"}
              onExpandAgent={
                readOnly ||
                data.type !== "AgentRef" ||
                !(data.values as { agent_id?: string } | undefined)?.agent_id
                  ? undefined
                  : handleExpandAgent
              }
            />
            <NodeStatusBadge status={runStatus} />
          </div>
          {!isMinimized && (
            <NodeDescription
              description={nodeDescription}
              onSave={updateDescription}
              readOnly={readOnly}
            />
          )}
        </div>

        {/* Collapsed to zero height rather than unmounted — each
            `NodeHandle` below stays a real DOM node so xyflow keeps
            tracking existing edges' anchor positions while minimized. */}
        <div
          className={cn(
            "py-2",
            isMinimized && "h-0 overflow-hidden py-0",
            readOnly && "pointer-events-none select-none"
          )}
        >
          {inputHandles.map((h) => (
            <HandleRow
              key={`in-${h.name}`}
              componentType={template.type}
              handle={h}
              direction="target"
              connected={connectedTargets.has(h.name)}
              field={
                handleFieldKey(h)
                  ? template.inputs[handleFieldKey(h)!]
                  : undefined
              }
              fieldKey={handleFieldKey(h)}
              value={
                handleFieldKey(h) ? data.values[handleFieldKey(h)!] : undefined
              }
              onFieldChange={updateValue}
              isPotentialTarget={
                !isDragOriginNode &&
                dragOrigin?.handleType === "source" &&
                !!dragOrigin.types &&
                handlesCompatible(dragOrigin.types, h.types as PortType[])
              }
              onHandleClick={() => handleClickToggle(h.name, "target")}
            />
          ))}

          {hasFields && (
            <NodeFieldList
              template={template}
              values={data.values}
              onFieldChange={updateValue}
              excludedKeys={[
                ...inputHandles.flatMap((h) => [
                  h.name,
                  ...(h.fallback_field ? [h.fallback_field] : []),
                ]),
                ...(toolModeKey ? [toolModeKey] : []),
              ]}
              className="nodrag flex flex-col gap-3 px-4 py-2"
            />
          )}

          {outputHandles.map((h) => (
            <HandleRow
              key={`out-${h.name}`}
              componentType={template.type}
              handle={h}
              direction="source"
              isPotentialTarget={
                !isDragOriginNode &&
                dragOrigin?.handleType === "target" &&
                !!dragOrigin.types &&
                handlesCompatible(h.types as PortType[], dragOrigin.types)
              }
              onHandleClick={() => handleClickToggle(h.name, "source")}
            />
          ))}
        </div>

        {!isMinimized && executionData && (
          <NodeExecutionDrawer
            nodeId={id}
            data={executionData}
            onToggle={() => updateNodeInternals(id)}
          />
        )}
      </NodeCard>
    );
  };
}
