"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  type NodeMouseHandler,
  type NodeChange,
  type OnNodeDrag,
  type OnInit,
} from "@xyflow/react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import "@xyflow/react/dist/style.css";

import { OrganizationDesignerInspector } from "@/components/organization/OrganizationDesignerInspector";
import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import {
  organizationTreeToFlowGraph,
  type OrganizationFlowEdge,
  type OrganizationFlowNode as OrganizationCanvasNode,
} from "@/components/organization/organizationGraph";
import type {
  CreateOrganization,
  DeleteOrganization,
  MoveOrganization,
  OrganizationMember,
  OrganizationNode,
  UpdateOrganization,
} from "@/components/organization/organizationTypes";
import { useOrganizationLayout } from "@/components/organization/useOrganizationLayout";
import { toast } from "@/hooks/useToast";
import { SvgExpand, SvgX } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationDesignerProps {
  organizations: OrganizationNode[];
  selectedOrg: OrganizationNode | null;
  members: OrganizationMember[];
  editable: boolean;
  capabilityLoading: boolean;
  canCreateRoot: boolean;
  canEditLayout: boolean;
  onClose: () => void;
  onSelectOrg: (organization: OrganizationNode) => void;
  onCreateOrg: CreateOrganization;
  onUpdateOrg: UpdateOrganization;
  onDeleteOrg: DeleteOrganization;
  onMoveOrg: MoveOrganization;
  onAddUser: (userId: string, role: string) => Promise<void>;
  onRoleChange: (userId: string, role: string) => Promise<void>;
  onRemoveUser: (userId: string) => Promise<void>;
  onAccessSaveComplete?: () => void | Promise<void>;
}

const nodeTypes = { organization: OrganizationFlowNode };

function indexOrganizations(organizations: OrganizationNode[]) {
  const byId = new Map<string, OrganizationNode>();
  function visit(organization: OrganizationNode) {
    byId.set(organization.id, organization);
    (organization.children ?? []).forEach(visit);
  }
  organizations.forEach(visit);
  return byId;
}

function OrganizationDesignerCanvas({
  organizations,
  selectedOrg,
  members,
  editable,
  capabilityLoading,
  canCreateRoot,
  canEditLayout,
  onClose,
  onSelectOrg,
  onCreateOrg,
  onUpdateOrg,
  onDeleteOrg,
  onMoveOrg,
  onAddUser,
  onRoleChange,
  onRemoveUser,
  onAccessSaveComplete,
}: OrganizationDesignerProps) {
  const {
    positions,
    writableOrganizationIds,
    status,
    error,
    isLoading,
    hasDirtyPositions,
    setPosition,
    flush,
    retry,
    discard,
    refresh,
  } = useOrganizationLayout();
  const flowInstanceRef = useRef<
    Parameters<OnInit<OrganizationCanvasNode, OrganizationFlowEdge>>[0] | null
  >(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const pointerDraggingNodeIdsRef = useRef(new Set<string>());
  const lastToastMessageRef = useRef<string | undefined>(undefined);
  const [isClosing, setIsClosing] = useState(false);
  const [closeAttemptFailed, setCloseAttemptFailed] = useState(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(
    Boolean(selectedOrg)
  );
  const organizationsById = useMemo(
    () => indexOrganizations(organizations),
    [organizations]
  );
  const canvasWritableOrganizationIds = useMemo(
    () =>
      canEditLayout ? writableOrganizationIds : new Set<string>(),
    [canEditLayout, writableOrganizationIds]
  );
  const graph = useMemo(
    () =>
      organizationTreeToFlowGraph(
        organizations,
        positions,
        canvasWritableOrganizationIds,
        selectedOrg?.id
      ),
    [canvasWritableOrganizationIds, organizations, positions, selectedOrg?.id]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);

  useEffect(() => {
    setNodes(graph.nodes);
  }, [graph.nodes, setNodes]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    previousFocusRef.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      previousFocusRef.current?.focus();
    };
  }, []);

  useEffect(() => {
    if (!error || error.message === lastToastMessageRef.current) return;
    lastToastMessageRef.current = error.message;
    toast.error(error.message);
  }, [error]);

  const requestClose = useCallback(async () => {
    if (isClosing) return;
    setIsClosing(true);
    const saved = await flush();
    if (saved) {
      onClose();
      return;
    }
    setCloseAttemptFailed(true);
    setIsClosing(false);
  }, [flush, isClosing, onClose]);

  const handleNodeClick: NodeMouseHandler<OrganizationCanvasNode> = useCallback(
    (_event, node) => {
      const organization = organizationsById.get(node.id);
      if (organization) {
        onSelectOrg(organization);
        setMobileInspectorOpen(true);
      }
    },
    [onSelectOrg, organizationsById]
  );

  const handleNodeDragStop: OnNodeDrag<OrganizationCanvasNode> = useCallback(
    (_event, node) => {
      if (!canEditLayout) return;
      setPosition(node.id, node.position);
    },
    [canEditLayout, setPosition]
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<OrganizationCanvasNode>[]) => {
      onNodesChange(
        canEditLayout
          ? changes
          : changes.filter((change) => change.type !== "position")
      );
      if (!canEditLayout) return;
      for (const change of changes) {
        if (change.type !== "position" || !change.position) continue;
        if (change.dragging) {
          pointerDraggingNodeIdsRef.current.add(change.id);
          continue;
        }
        if (pointerDraggingNodeIdsRef.current.delete(change.id)) continue;
        if (change.dragging === false) setPosition(change.id, change.position);
      }
    },
    [canEditLayout, onNodesChange, setPosition]
  );

  const handleInit: OnInit<OrganizationCanvasNode, OrganizationFlowEdge> = useCallback((instance) => {
    flowInstanceRef.current = instance;
  }, []);

  const handleRetry = useCallback(async () => {
    const saved =
      status === "error" || hasDirtyPositions
        ? await retry()
        : Boolean(await refresh());
    if (saved && closeAttemptFailed) onClose();
  }, [closeAttemptFailed, hasDirtyPositions, onClose, refresh, retry, status]);

  const statusLabel = isLoading
    ? "Loading layout…"
    : status === "saving" || isClosing
      ? "Saving…"
      : status === "saved"
        ? "Saved"
        : status === "error"
          ? "Save failed"
          : hasDirtyPositions
            ? "Unsaved changes"
            : "Ready";

  return (
    <DialogPrimitive.Root open>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={cn("fixed inset-0 z-[99] bg-background-neutral-01")} />
        <DialogPrimitive.Content
          ref={dialogRef}
          tabIndex={-1}
          aria-label="Organization designer"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            dialogRef.current?.focus();
          }}
          onEscapeKeyDown={(event) => {
            event.preventDefault();
            void requestClose();
          }}
          className={cn(
            "fixed inset-0 z-[100] flex flex-col bg-background-neutral-01 outline-none"
          )}
        >
      <header
        className={cn(
          "flex min-h-14 items-center gap-3 border-b border-border-02 bg-background-neutral-00 px-4"
        )}
      >
        <DialogPrimitive.Title className={cn("sr-only")}>
          Organization designer
        </DialogPrimitive.Title>
        <Text headingH3 text04 as="p">
          Organizations
        </Text>
        <Text secondaryMono text03 className={cn("ml-2")}>
          {statusLabel}
        </Text>
        {error && (
          <Text secondaryBody text02 className={cn("min-w-0 truncate")}>
            {error.message}
          </Text>
        )}
        <div className={cn("ml-auto flex items-center gap-2")}>
          {error && (
            <Button secondary size="md" onClick={() => void handleRetry()}>
              Retry
            </Button>
          )}
          {closeAttemptFailed && (
            <Button
              danger
              secondary
              size="md"
              onClick={() => {
                discard();
                onClose();
              }}
            >
              Discard and close
            </Button>
          )}
          <IconButton
            icon={SvgExpand}
            tooltip="Fit view"
            aria-label="Fit view"
            tertiary
            onClick={() => void flowInstanceRef.current?.fitView({ padding: 0.2 })}
          />
          <IconButton
            icon={SvgX}
            tooltip="Close designer"
            aria-label="Close designer"
            tertiary
            disabled={isClosing}
            onClick={() => void requestClose()}
          />
        </div>
      </header>

      <div className={cn("relative flex min-h-0 flex-1")}>
        <div className={cn("relative min-w-0 flex-1")}>
          <ReactFlow<OrganizationCanvasNode, OrganizationFlowEdge>
            nodes={nodes}
            edges={graph.edges}
            nodeTypes={nodeTypes}
            nodesConnectable={false}
            edgesFocusable={false}
            deleteKeyCode={null}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.2}
            maxZoom={2}
            onInit={handleInit}
            onNodeClick={handleNodeClick}
            onNodesChange={handleNodesChange}
            onNodeDragStop={handleNodeDragStop}
          >
            <Background
              color="var(--border-01)"
              gap={24}
              size={1}
            />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeColor="var(--background-neutral-04)"
              maskColor="color-mix(in srgb, var(--background-neutral-01) 78%, transparent)"
            />
          </ReactFlow>
          {isLoading && (
            <div
              className={cn(
                "pointer-events-none absolute inset-0 flex items-center justify-center bg-background-neutral-01"
              )}
            >
              <Text text03>Loading organization map…</Text>
            </div>
          )}
          {!isLoading && organizations.length === 0 && canCreateRoot && (
            <div className={cn("absolute inset-0 flex items-center justify-center")}>
              <Button
                action
                primary
                size="md"
                onClick={() => {
                  const name = window.prompt("Enter organization name:");
                  if (name?.trim()) void onCreateOrg(null, name.trim());
                }}
              >
                Create root organization
              </Button>
            </div>
          )}
          {selectedOrg && !mobileInspectorOpen && (
            <Button
              secondary
              size="md"
              className={cn("absolute right-4 top-4 z-10 md:hidden")}
              onClick={() => setMobileInspectorOpen(true)}
            >
              Show inspector
            </Button>
          )}
        </div>

        <OrganizationDesignerInspector
          key={selectedOrg?.id ?? "no-selection"}
          organization={selectedOrg}
          organizations={organizations}
          members={members}
          editable={editable}
          capabilityLoading={capabilityLoading}
          mobileOpen={mobileInspectorOpen}
          onBackToMap={() => setMobileInspectorOpen(false)}
          onAccessSaveComplete={onAccessSaveComplete}
          onCreateOrg={onCreateOrg}
          onUpdateOrg={onUpdateOrg}
          onDeleteOrg={onDeleteOrg}
          onMoveOrg={onMoveOrg}
          onAddUser={onAddUser}
          onRoleChange={onRoleChange}
          onRemoveUser={onRemoveUser}
        />
      </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function OrganizationDesigner(props: OrganizationDesignerProps) {
  return (
    <ReactFlowProvider>
      <OrganizationDesignerCanvas {...props} />
    </ReactFlowProvider>
  );
}
