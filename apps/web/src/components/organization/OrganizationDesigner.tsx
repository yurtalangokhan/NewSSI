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
import {
  SvgArrowExchange,
  SvgArrowUpDown,
  SvgChevronLeft,
  SvgChevronRight,
} from "@opal/icons";
import { useTranslation } from "react-i18next";
import "@xyflow/react/dist/style.css";

import { OrganizationDesignerInspector } from "@/components/organization/OrganizationDesignerInspector";
import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import { OrganizationMoveConfirmationModal } from "@/components/organization/OrganizationMoveConfirmationModal";
import {
  organizationTreeToFlowGraph,
  organizationTreeToLayoutPositions,
  inferOrganizationLayoutOrientation,
  repositionOrganizationSubtree,
  type OrganizationLayoutOrientation,
  type OrganizationFlowEdge,
  type OrganizationFlowNode as OrganizationCanvasNode,
} from "@/components/organization/organizationGraph";
import type {
  CreateOrganization,
  DeleteOrganization,
  MoveOrganization,
  OrganizationMember,
  OrganizationMembersByUnit,
  OrganizationNode,
  UpdateOrganization,
} from "@/components/organization/organizationTypes";
import {
  getOrganizationMatches,
  flattenOrganizations,
  normalizeOrganizationSearch,
} from "@/components/organization/organizationSearch";
import { useOrganizationLayout } from "@/components/organization/useOrganizationLayout";
import { toast } from "@/hooks/useToast";
import { SvgExpand, SvgOrganization, SvgX } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
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
  showMembers?: boolean;
  membersByOrganizationId?: OrganizationMembersByUnit;
  onShowMembersChange?: (show: boolean) => void;
  membersLoading?: boolean;
}

const nodeTypes = { organization: OrganizationFlowNode };
const DRAFT_NODE_ID = "__new-organization__";
const EMPTY_MEMBERS_BY_ORGANIZATION: OrganizationMembersByUnit = {};

function indexOrganizations(organizations: OrganizationNode[]) {
  const byId = new Map<string, OrganizationNode>();
  function visit(organization: OrganizationNode) {
    byId.set(organization.id, organization);
    (organization.children ?? []).forEach(visit);
  }
  organizations.forEach(visit);
  return byId;
}

function descendantIds(organization: OrganizationNode) {
  return new Set(
    flattenOrganizations(organization.children ?? []).map((item) => item.id)
  );
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
  showMembers = false,
  membersByOrganizationId = EMPTY_MEMBERS_BY_ORGANIZATION,
  onShowMembersChange,
  membersLoading = false,
}: OrganizationDesignerProps) {
  const { t, i18n } = useTranslation();
  const {
    positions,
    writableOrganizationIds,
    status,
    error,
    isLoading,
    hasDirtyPositions,
    setPosition,
    replacePositionsAndSave,
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
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(-1);
  const [pendingMove, setPendingMove] = useState<{
    organization: OrganizationNode;
    parent: OrganizationNode;
  } | null>(null);
  const [pendingLayoutReset, setPendingLayoutReset] =
    useState<OrganizationLayoutOrientation | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [draftParentId, setDraftParentId] = useState<string | null | undefined>(
    undefined
  );
  const [nodeAction, setNodeAction] = useState<
    { id: string; mode: "rename" | "delete" } | undefined
  >(undefined);
  const organizationsById = useMemo(
    () => indexOrganizations(organizations),
    [organizations]
  );
  const allOrganizations = useMemo(
    () => flattenOrganizations(organizations),
    [organizations]
  );
  const searchMatches = useMemo(
    () => getOrganizationMatches(organizations, searchQuery, i18n.language),
    [i18n.language, organizations, searchQuery]
  );
  const hasSearch = Boolean(
    normalizeOrganizationSearch(searchQuery, i18n.language)
  );
  const matchingOrganizationIds = useMemo(
    () => new Set(searchMatches.map((organization) => organization.id)),
    [searchMatches]
  );
  const canvasWritableOrganizationIds = useMemo(
    () => (canEditLayout ? writableOrganizationIds : new Set<string>()),
    [canEditLayout, writableOrganizationIds]
  );
  const layoutOrientation = useMemo(
    () => inferOrganizationLayoutOrientation(organizations, positions),
    [organizations, positions]
  );
  const baseGraph = useMemo(
    () =>
      organizationTreeToFlowGraph(
        organizations,
        positions,
        canvasWritableOrganizationIds,
        selectedOrg?.id,
        layoutOrientation
      ),
    [
      canvasWritableOrganizationIds,
      layoutOrientation,
      organizations,
      positions,
      selectedOrg?.id,
    ]
  );
  const startChildCreation = useCallback((parentId: string | null) => {
    setNodeAction(undefined);
    setDraftParentId(parentId);
  }, []);
  const beginNodeDelete = useCallback((organizationId: string) => {
    setDraftParentId(undefined);
    setNodeAction({ id: organizationId, mode: "delete" });
    setMobileInspectorOpen(false);
  }, []);
  const cancelChildCreation = useCallback(() => {
    setDraftParentId(undefined);
  }, []);
  const submitChildCreation = useCallback(
    async (name: string) => {
      if (draftParentId === undefined) return;
      await onCreateOrg(draftParentId, name);
      setDraftParentId(undefined);
    },
    [draftParentId, onCreateOrg]
  );
  const graph = useMemo(() => {
    const nodes: OrganizationCanvasNode[] = baseGraph.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        searchMatch: hasSearch && matchingOrganizationIds.has(node.id),
        searchDimmed: hasSearch && !matchingOrganizationIds.has(node.id),
        isDropTarget: dropTargetId === node.id,
        members: showMembers ? membersByOrganizationId[node.id] ?? [] : [],
        parentOptions: allOrganizations
          .filter((candidate) => {
            const source = organizationsById.get(node.id);
            return (
              source &&
              candidate.id !== node.id &&
              !descendantIds(source).has(candidate.id)
            );
          })
          .map(({ id, name }) => ({ id, name })),
        onRequestMove: (parentId: string) => {
          const organization = organizationsById.get(node.id);
          const parent = organizationsById.get(parentId);
          if (organization && parent && organization.parent_id !== parent.id)
            setPendingMove({ organization, parent });
        },
        canAddChild:
          node.id === selectedOrg?.id && editable && !capabilityLoading,
        canManage:
          node.id === selectedOrg?.id && editable && !capabilityLoading,
        actionMode: nodeAction?.id === node.id ? nodeAction.mode : undefined,
        onAddChild: () => startChildCreation(node.id),
        onBeginDelete: () => beginNodeDelete(node.id),
        onBeginRename: () => {
          setDraftParentId(undefined);
          setNodeAction({ id: node.id, mode: "rename" });
        },
        onCancelAction: () => setNodeAction(undefined),
        onDelete: () => onDeleteOrg(node.id),
        onRename: (name: string) => onUpdateOrg(node.id, { name }),
      },
    }));
    const edges = baseGraph.edges.map((edge) => ({
      ...edge,
      style: {
        ...edge.style,
        opacity: hasSearch
          ? matchingOrganizationIds.has(edge.source) ||
            matchingOrganizationIds.has(edge.target)
            ? 0.62
            : 0.16
          : 1,
      },
    }));

    if (draftParentId !== undefined) {
      const parentNode =
        draftParentId === null
          ? undefined
          : nodes.find((node) => node.id === draftParentId);
      nodes.push({
        id: DRAFT_NODE_ID,
        type: "organization",
        position: parentNode
          ? { x: parentNode.position.x, y: parentNode.position.y + 180 }
          : { x: 0, y: 0 },
        selectable: false,
        draggable: false,
        data: {
          organizationId: DRAFT_NODE_ID,
          name: t("admin.organizations.designer.newOrganization"),
          path: "",
          childCount: 0,
          readOnly: true,
          layoutOrientation,
          isDraft: true,
          onCancelDraft: cancelChildCreation,
          onSubmitDraft: submitChildCreation,
        },
      });
      if (draftParentId !== null) {
        edges.push({
          id: `${draftParentId}-${DRAFT_NODE_ID}`,
          source: draftParentId,
          target: DRAFT_NODE_ID,
          sourceHandle: layoutOrientation === "horizontal" ? "right" : "bottom",
          targetHandle: layoutOrientation === "horizontal" ? "left" : "top",
          type: "smoothstep",
          selectable: false,
          focusable: false,
          data: { active: true },
          style: {
            stroke: "var(--action-link-05)",
            strokeWidth: 2,
            opacity: 1,
          },
        });
      }
    }

    return { nodes, edges };
  }, [
    baseGraph,
    beginNodeDelete,
    cancelChildCreation,
    capabilityLoading,
    draftParentId,
    editable,
    allOrganizations,
    dropTargetId,
    hasSearch,
    matchingOrganizationIds,
    layoutOrientation,
    membersByOrganizationId,
    organizationsById,
    nodeAction,
    onDeleteOrg,
    onUpdateOrg,
    selectedOrg?.id,
    showMembers,
    startChildCreation,
    submitChildCreation,
    t,
  ]);
  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);

  useEffect(() => {
    setNodes(graph.nodes);
  }, [graph.nodes, setNodes]);

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
      const organization = organizationsById.get(node.id);
      const targetNode = flowInstanceRef.current
        ?.getIntersectingNodes?.(node)
        .find((candidate) => {
          const parent = organizationsById.get(candidate.id);
          return (
            parent &&
            organization &&
            parent.id !== organization.id &&
            !descendantIds(organization).has(parent.id)
          );
        });
      const parent = targetNode && organizationsById.get(targetNode.id);
      setDropTargetId(null);
      if (organization && parent && organization.parent_id !== parent.id) {
        setPendingMove({ organization, parent });
        setNodes(graph.nodes);
        return;
      }
      setPosition(node.id, node.position);
    },
    [canEditLayout, graph.nodes, organizationsById, setNodes, setPosition]
  );

  const handleNodeDrag: OnNodeDrag<OrganizationCanvasNode> = useCallback(
    (_event, node) => {
      const organization = organizationsById.get(node.id);
      const target = flowInstanceRef.current
        ?.getIntersectingNodes?.(node)
        .find((candidate) => {
          const parent = organizationsById.get(candidate.id);
          return (
            parent &&
            organization &&
            parent.id !== organization.id &&
            !descendantIds(organization).has(parent.id)
          );
        });
      setDropTargetId(target?.id ?? null);
    },
    [organizationsById]
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

  const handleInit: OnInit<OrganizationCanvasNode, OrganizationFlowEdge> =
    useCallback((instance) => {
      flowInstanceRef.current = instance;
    }, []);

  const handleRetry = useCallback(async () => {
    const saved =
      status === "error" || hasDirtyPositions
        ? await retry()
        : Boolean(await refresh());
    if (saved && closeAttemptFailed) onClose();
  }, [closeAttemptFailed, hasDirtyPositions, onClose, refresh, retry, status]);

  const confirmLayoutReset = useCallback(async () => {
    if (!pendingLayoutReset) return;
    const nextPositions = organizationTreeToLayoutPositions(
      organizations,
      pendingLayoutReset
    );
    setPendingLayoutReset(null);
    const saved = await replacePositionsAndSave(nextPositions);
    if (!saved) return;
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        position: nextPositions[node.id] ?? node.position,
      }))
    );
    const fittedNodes = graph.nodes.map((node) => ({
      ...node,
      position: nextPositions[node.id] ?? node.position,
    }));
    void flowInstanceRef.current?.fitView({
      nodes: fittedNodes,
      padding: 0.2,
      duration: 300,
    });
    toast.success(t("admin.organizations.designer.resetSuccess"));
  }, [
    graph.nodes,
    organizations,
    pendingLayoutReset,
    replacePositionsAndSave,
    setNodes,
    t,
  ]);

  const confirmOrganizationMove = useCallback(async () => {
    if (!pendingMove) return;
    const move = pendingMove;
    setPendingMove(null);
    const moved = await onMoveOrg(move.organization.id, move.parent.id);
    if (!moved) return;

    const movedPositions = repositionOrganizationSubtree(
      organizations,
      positions,
      move.organization.id,
      move.parent.id,
      layoutOrientation
    );
    if (Object.keys(movedPositions).length === 0) return;
    const saved = await replacePositionsAndSave(movedPositions);
    if (!saved) return;

    let movedNode: OrganizationCanvasNode | undefined;
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        const position = movedPositions[node.id];
        if (!position) return node;
        const updatedNode = { ...node, position };
        if (node.id === move.organization.id) movedNode = updatedNode;
        return updatedNode;
      })
    );
    const graphNode = graph.nodes.find(
      (node) => node.id === move.organization.id
    );
    if (!movedNode && graphNode) {
      movedNode = {
        ...graphNode,
        position: movedPositions[graphNode.id] ?? graphNode.position,
      };
    }
    if (movedNode) {
      void flowInstanceRef.current?.fitView({
        nodes: [movedNode],
        padding: 0.8,
        duration: 300,
      });
    }
  }, [
    graph.nodes,
    layoutOrientation,
    onMoveOrg,
    organizations,
    pendingMove,
    positions,
    replacePositionsAndSave,
    setNodes,
  ]);

  const statusLabel = isLoading
    ? t("admin.organizations.designer.loadingLayout")
    : status === "saving" || isClosing
      ? t("admin.organizations.designer.saving")
      : status === "saved"
        ? t("admin.organizations.designer.saved")
        : status === "error"
          ? t("admin.organizations.designer.saveFailed")
          : hasDirtyPositions
            ? t("admin.organizations.designer.unsavedChanges")
            : t("admin.organizations.designer.ready");

  const navigateSearch = useCallback(
    (direction: 1 | -1) => {
      if (searchMatches.length === 0) return;
      const nextIndex =
        activeSearchMatchIndex < 0
          ? direction === 1
            ? 0
            : searchMatches.length - 1
          : (activeSearchMatchIndex + direction + searchMatches.length) %
            searchMatches.length;
      const organization = searchMatches[nextIndex]!;
      const flowNode = graph.nodes.find((node) => node.id === organization.id);
      setActiveSearchMatchIndex(nextIndex);
      onSelectOrg(organization);
      setMobileInspectorOpen(true);
      if (flowNode) {
        void flowInstanceRef.current?.fitView({
          nodes: [flowNode],
          padding: 0.8,
          duration: 300,
        });
      }
    },
    [activeSearchMatchIndex, graph.nodes, onSelectOrg, searchMatches]
  );

  return (
    <DialogPrimitive.Root open>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn("fixed inset-0 z-[99] bg-background-neutral-01")}
        />
        <DialogPrimitive.Content
          ref={dialogRef}
          tabIndex={-1}
          aria-label={t("admin.organizations.designer.title")}
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            dialogRef.current?.focus();
          }}
          onEscapeKeyDown={(event) => {
            event.preventDefault();
            if (searchQuery) {
              setSearchQuery("");
              setActiveSearchMatchIndex(-1);
              return;
            }
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
              {t("admin.organizations.designer.title")}
            </DialogPrimitive.Title>
            <Text headingH3 text04 as="p">
              {t("admin.organizations.tree.title")}
            </Text>
            <Text secondaryMono text03 className={cn("ml-2")}>
              {statusLabel}
            </Text>
            {error && (
              <Text secondaryBody text02 className={cn("min-w-0 truncate")}>
                {error.message}
              </Text>
            )}
            <div
              className={cn(
                "ml-auto flex w-full max-w-md items-center gap-2 max-md:max-w-xs"
              )}
            >
              <InputTypeIn
                aria-label={t("admin.organizations.tree.searchLabel")}
                className={cn(
                  "border border-border-02 bg-background-neutral-01 shadow-sm transition-[border-color,box-shadow] duration-200 focus-within:border-action-link-05 focus-within:ring-1 focus-within:ring-action-link-05 motion-reduce:transition-none"
                )}
                leftSearchIcon
                placeholder={t("admin.organizations.tree.searchPlaceholder")}
                value={searchQuery}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                  setActiveSearchMatchIndex(-1);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.stopPropagation();
                    navigateSearch(event.shiftKey ? -1 : 1);
                  } else if (event.key === "Escape") {
                    event.preventDefault();
                    event.stopPropagation();
                    setSearchQuery("");
                    setActiveSearchMatchIndex(-1);
                  }
                }}
              />
              {searchQuery.trim() && (
                <div className={cn("flex shrink-0 items-center gap-1")}>
                  <IconButton
                    aria-label={t("admin.organizations.tree.previousResult")}
                    disabled={!searchMatches.length}
                    icon={SvgChevronLeft}
                    small
                    tertiary
                    tooltip={t("admin.organizations.tree.previousResult")}
                    onClick={() => navigateSearch(-1)}
                  />
                  <Text
                    aria-live="polite"
                    secondaryMono
                    text04
                    className={cn(
                      "min-w-12 rounded-08 bg-background-neutral-03 px-2 py-1 text-center"
                    )}
                  >
                    {searchMatches.length
                      ? activeSearchMatchIndex >= 0
                        ? activeSearchMatchIndex + 1
                        : 1
                      : 0}{" "}
                    / {searchMatches.length}
                  </Text>
                  <IconButton
                    aria-label={t("admin.organizations.tree.nextResult")}
                    disabled={!searchMatches.length}
                    icon={SvgChevronRight}
                    small
                    tertiary
                    tooltip={t("admin.organizations.tree.nextResult")}
                    onClick={() => navigateSearch(1)}
                  />
                </div>
              )}
            </div>
            <div className={cn("flex items-center gap-2")}>
              {onShowMembersChange && (
                <Button
                  aria-pressed={showMembers}
                  disabled={membersLoading}
                  secondary
                  size="md"
                  onClick={() => onShowMembersChange(!showMembers)}
                >
                  {t(
                    membersLoading
                      ? "admin.organizations.tree.loadingMembers"
                      : showMembers
                        ? "admin.organizations.tree.hideMembers"
                        : "admin.organizations.tree.showMembers"
                  )}
                </Button>
              )}
              {error && (
                <Button secondary size="md" onClick={() => void handleRetry()}>
                  {t("admin.organizations.actions.retry")}
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
                  {t("admin.organizations.designer.discardAndClose")}
                </Button>
              )}
              <IconButton
                icon={SvgExpand}
                tooltip={t("admin.organizations.designer.fitView")}
                aria-label={t("admin.organizations.designer.fitView")}
                tertiary
                onClick={() =>
                  void flowInstanceRef.current?.fitView({ padding: 0.2 })
                }
              />
              <IconButton
                icon={SvgX}
                tooltip={t("admin.organizations.designer.close")}
                aria-label={t("admin.organizations.designer.close")}
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
                proOptions={{ hideAttribution: true }}
                onInit={handleInit}
                onNodeClick={handleNodeClick}
                onNodesChange={handleNodesChange}
                onNodeDrag={handleNodeDrag}
                onNodeDragStop={handleNodeDragStop}
              >
                <Background color="var(--border-01)" gap={24} size={1} />
                <Controls showInteractive={false} />
                <MiniMap
                  pannable
                  zoomable
                  nodeColor="var(--background-neutral-04)"
                  maskColor="color-mix(in srgb, var(--background-neutral-01) 78%, transparent)"
                />
              </ReactFlow>
              {canEditLayout && organizations.length > 0 && (
                <div
                  className={cn(
                    "absolute right-4 top-4 z-10 flex items-center gap-1 rounded-12 border border-border-02 bg-background-neutral-00 p-1 shadow-md"
                  )}
                >
                  <IconButton
                    aria-label={t("admin.organizations.designer.resetVertical")}
                    disabled={status === "saving"}
                    icon={SvgArrowUpDown}
                    tertiary
                    tooltip={t("admin.organizations.designer.resetVertical")}
                    onClick={() => setPendingLayoutReset("vertical")}
                  />
                  <IconButton
                    aria-label={t(
                      "admin.organizations.designer.resetHorizontal"
                    )}
                    disabled={status === "saving"}
                    icon={SvgArrowExchange}
                    tertiary
                    tooltip={t("admin.organizations.designer.resetHorizontal")}
                    onClick={() => setPendingLayoutReset("horizontal")}
                  />
                </div>
              )}
              {!isLoading &&
                organizations.length === 0 &&
                canCreateRoot &&
                draftParentId === undefined && (
                  <div
                    className={cn(
                      "absolute inset-0 flex items-center justify-center"
                    )}
                  >
                    <Button
                      action
                      primary
                      size="md"
                      onClick={() => startChildCreation(null)}
                    >
                      {t("admin.organizations.designer.createRoot")}
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
                  {t("admin.organizations.designer.showInspector")}
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
              onBeginCreateChild={startChildCreation}
              onBeginDelete={beginNodeDelete}
              onAccessSaveComplete={onAccessSaveComplete}
              onUpdateOrg={onUpdateOrg}
              onMoveOrg={onMoveOrg}
              onAddUser={onAddUser}
              onRoleChange={onRoleChange}
              onRemoveUser={onRemoveUser}
            />
          </div>
          {pendingMove && (
            <OrganizationMoveConfirmationModal
              organizationName={pendingMove.organization.name}
              currentParentName={
                organizationsById.get(pendingMove.organization.parent_id ?? "")
                  ?.name ?? t("admin.organizations.moveConfirm.noParent")
              }
              newParentName={pendingMove.parent.name}
              onCancel={() => setPendingMove(null)}
              onConfirm={() => void confirmOrganizationMove()}
            />
          )}
          {pendingLayoutReset && (
            <ConfirmationModalLayout
              icon={SvgOrganization}
              title={t("admin.organizations.designer.resetTitle")}
              onClose={() => setPendingLayoutReset(null)}
              submit={
                <Button
                  action
                  primary
                  onClick={() => void confirmLayoutReset()}
                >
                  {t("admin.organizations.designer.resetConfirm")}
                </Button>
              }
            >
              <Text mainUiBody text04>
                {t("admin.organizations.designer.resetDescription", {
                  orientation: t(
                    pendingLayoutReset === "vertical"
                      ? "admin.organizations.designer.resetOrientationVertical"
                      : "admin.organizations.designer.resetOrientationHorizontal"
                  ),
                })}
              </Text>
            </ConfirmationModalLayout>
          )}
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
