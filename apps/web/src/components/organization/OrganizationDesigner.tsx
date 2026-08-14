"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useNodesState,
  type NodeMouseHandler,
  type NodeChange,
  type OnNodeDrag,
  type OnInit,
} from "@xyflow/react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { SvgArrowExchange, SvgArrowUpDown } from "@opal/icons";
import { useTranslation } from "react-i18next";
import { useTheme } from "next-themes";
import "@xyflow/react/dist/style.css";

import { OrganizationDesignerInspector } from "@/components/organization/OrganizationDesignerInspector";
import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import { OrganizationMoveConfirmationModal } from "@/components/organization/OrganizationMoveConfirmationModal";
import { OrganizationSearchCombobox } from "@/components/organization/OrganizationSearchCombobox";
import {
  organizationTreeToFlowGraph,
  organizationTreeToLayoutPositions,
  inferOrganizationLayoutOrientation,
  repositionOrganizationSubtree,
  isNodeSubtreeExpanded,
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
  OrganizationSearchProps,
  UpdateOrganization,
} from "@/components/organization/organizationTypes";
import {
  getOrganizationMatches,
  flattenOrganizations,
  normalizeOrganizationSearch,
} from "@/components/organization/organizationSearch";
import {
  MAX_ORGANIZATION_LAYOUT_POSITIONS,
  useOrganizationLayout,
  type OrganizationPositionMap,
} from "@/components/organization/useOrganizationLayout";
import { toast } from "@/hooks/useToast";
import { SvgExpand, SvgOrganization, SvgX } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationDesignerProps extends Partial<OrganizationSearchProps> {
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
  onExpandOrg?: (orgId: string) => void | Promise<void>;
}

const nodeTypes = { organization: OrganizationFlowNode };
const DRAFT_NODE_ID = "__new-organization__";
const EMPTY_MEMBERS_BY_ORGANIZATION: OrganizationMembersByUnit = {};
const COMPLETE_TREE_FETCH_ERROR = "complete-tree-fetch-failed";
const COMPLETED_RESET_PROGRESS_VISIBLE_MS = 400;
const NODE_CLOSE_ANIMATION_MS = 200;

type CompleteResetValidationError = "incomplete-access" | "too-large";

async function fetchCompleteOrganizationTree() {
  const response = await fetch("/api/user-service/organizations/tree");
  if (!response.ok) throw new Error(COMPLETE_TREE_FETCH_ERROR);
  const data = (await response.json()) as
    | { roots: OrganizationNode[] }
    | OrganizationNode[];
  const organizations = Array.isArray(data) ? data : data.roots;
  if (!Array.isArray(organizations)) {
    throw new Error(COMPLETE_TREE_FETCH_ERROR);
  }
  return organizations;
}

function validateCompleteReset(
  organizationIds: string[],
  writableOrganizationIds: ReadonlySet<string>
): CompleteResetValidationError | undefined {
  if (organizationIds.length > MAX_ORGANIZATION_LAYOUT_POSITIONS) {
    return "too-large";
  }
  if (
    organizationIds.some(
      (organizationId) => !writableOrganizationIds.has(organizationId)
    )
  ) {
    return "incomplete-access";
  }
}

function wait(durationMs: number) {
  return new Promise((resolve) => setTimeout(resolve, durationMs));
}

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
  onExpandOrg,
  searchResults = [],
  searchLoading = false,
  searchError = null,
  resultsLimited = false,
  revealLoading = false,
  onSearch = () => {},
  onRevealResult = () => {},
  revealRequest = null,
  onRevealReady = onSelectOrg,
}: OrganizationDesignerProps) {
  const { t, i18n } = useTranslation();
  const { resolvedTheme } = useTheme();
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
  const resetInProgressRef = useRef(false);
  const resetFitStartedRef = useRef(false);
  const resetViewportResolverRef = useRef<(() => void) | null>(null);
  const completedRevealIdRef = useRef<number | null>(null);
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
  const [resetProgress, setResetProgress] = useState<{
    percent: number;
    label: string;
  } | null>(null);
  const [pendingResetPositions, setPendingResetPositions] =
    useState<OrganizationPositionMap | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [draftParentId, setDraftParentId] = useState<string | null | undefined>(
    undefined
  );
  const [nodeAction, setNodeAction] = useState<
    { id: string; mode: "rename" | "delete" } | undefined
  >(undefined);
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(
    () => new Set()
  );
  const [collapsedNodeIds, setCollapsedNodeIds] = useState<Set<string>>(
    () => new Set()
  );
  // Subtree roots mid-collapse: their children stay mounted (fading out via
  // CSS) until the timeout below actually removes them from the graph, so
  // the collapse reads as a transition instead of an instant disappearance.
  const [closingNodeIds, setClosingNodeIds] = useState<Set<string>>(
    () => new Set()
  );
  const closeTimeoutsRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  useEffect(
    () => () => {
      closeTimeoutsRef.current.forEach((timeout) => clearTimeout(timeout));
      closeTimeoutsRef.current.clear();
    },
    []
  );

  const handleToggleSubtree = useCallback(
    (nodeId: string, currentChildrenLength: number) => {
      const currentlyExpanded = isNodeSubtreeExpanded(
        nodeId,
        currentChildrenLength,
        expandedNodeIds,
        collapsedNodeIds
      );

      const pendingClose = closeTimeoutsRef.current.get(nodeId);
      if (pendingClose) {
        clearTimeout(pendingClose);
        closeTimeoutsRef.current.delete(nodeId);
      }

      if (currentlyExpanded) {
        setClosingNodeIds((prev) => new Set(prev).add(nodeId));
        const timeout = setTimeout(() => {
          setCollapsedNodeIds((prev) => new Set(prev).add(nodeId));
          setExpandedNodeIds((prev) => {
            const next = new Set(prev);
            next.delete(nodeId);
            return next;
          });
          setClosingNodeIds((prev) => {
            const next = new Set(prev);
            next.delete(nodeId);
            return next;
          });
          closeTimeoutsRef.current.delete(nodeId);
        }, NODE_CLOSE_ANIMATION_MS);
        closeTimeoutsRef.current.set(nodeId, timeout);
      } else {
        setClosingNodeIds((prev) => {
          if (!prev.has(nodeId)) return prev;
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
        setExpandedNodeIds((prev) => new Set(prev).add(nodeId));
        setCollapsedNodeIds((prev) => {
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
        if (onExpandOrg) {
          void onExpandOrg(nodeId);
        }
      }
    },
    [collapsedNodeIds, expandedNodeIds, onExpandOrg]
  );
  const organizationsById = useMemo(
    () => indexOrganizations(organizations),
    [organizations]
  );
  const allOrganizations = useMemo(
    () => flattenOrganizations(organizations),
    [organizations]
  );
  const closingDescendantIds = useMemo(() => {
    const ids = new Set<string>();
    closingNodeIds.forEach((nodeId) => {
      const organization = organizationsById.get(nodeId);
      if (!organization) return;
      descendantIds(organization).forEach((id) => ids.add(id));
    });
    return ids;
  }, [closingNodeIds, organizationsById]);
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
        layoutOrientation,
        expandedNodeIds,
        collapsedNodeIds
      ),
    [
      canvasWritableOrganizationIds,
      collapsedNodeIds,
      expandedNodeIds,
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
        onToggleSubtree: () =>
          handleToggleSubtree(
            node.id,
            (organizationsById.get(node.id)?.children ?? []).length
          ),
        searchMatch: hasSearch && matchingOrganizationIds.has(node.id),
        searchDimmed: hasSearch && !matchingOrganizationIds.has(node.id),
        closing: closingDescendantIds.has(node.id),
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
        opacity: closingDescendantIds.has(edge.target)
          ? 0
          : hasSearch
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
    closingDescendantIds,
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
  const nodesInitialized = useNodesInitialized();

  useEffect(() => {
    setNodes(graph.nodes);
  }, [graph.nodes, setNodes]);

  const commitResetPositions = useCallback(
    (nextPositions: OrganizationPositionMap) =>
      new Promise<void>((resolve) => {
        resetViewportResolverRef.current = resolve;
        resetFitStartedRef.current = false;
        setPendingResetPositions(nextPositions);
        setNodes((currentNodes) =>
          currentNodes.map((node) => ({
            ...node,
            position: nextPositions[node.id] ?? node.position,
          }))
        );
      }),
    [setNodes]
  );

  useEffect(() => {
    if (
      !pendingResetPositions ||
      !nodesInitialized ||
      resetFitStartedRef.current
    ) {
      return;
    }
    const positionsCommitted = nodes.every((node) => {
      const expectedPosition = pendingResetPositions[node.id];
      return (
        !expectedPosition ||
        (node.position.x === expectedPosition.x &&
          node.position.y === expectedPosition.y)
      );
    });
    if (!positionsCommitted) return;

    resetFitStartedRef.current = true;
    setResetProgress({
      percent: 90,
      label: t("admin.organizations.designer.resetProgressRendered"),
    });
    void (async () => {
      await flowInstanceRef.current?.fitView({
        nodes,
        padding: 0.2,
        duration: 300,
      });
      setPendingResetPositions(null);
      resetFitStartedRef.current = false;
      resetViewportResolverRef.current?.();
      resetViewportResolverRef.current = null;
    })();
  }, [nodes, nodesInitialized, pendingResetPositions, t]);



  useEffect(() => {
    if (!revealRequest || completedRevealIdRef.current === revealRequest.id) {
      return;
    }
    setExpandedNodeIds((current) => {
      const next = new Set(current);
      revealRequest.ancestorIds.forEach((id) => next.add(id));
      return next;
    });
    setCollapsedNodeIds((current) => {
      const next = new Set(current);
      revealRequest.ancestorIds.forEach((id) => next.delete(id));
      return next;
    });
  }, [revealRequest]);

  useEffect(() => {
    if (!revealRequest || completedRevealIdRef.current === revealRequest.id) {
      return;
    }
    const targetNode = graph.nodes.find(
      ({ id }) => id === revealRequest.result.id
    );
    if (!targetNode) return;
    const organization = organizationsById.get(revealRequest.result.id);
    if (!organization) return;
    completedRevealIdRef.current = revealRequest.id;
    onRevealReady(organization);
    setMobileInspectorOpen(true);
    void flowInstanceRef.current?.fitView({
      nodes: [targetNode],
      padding: 0.8,
      duration: 300,
    });
  }, [graph.nodes, onRevealReady, organizationsById, revealRequest]);

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
    if (
      !error ||
      resetInProgressRef.current ||
      error.message === lastToastMessageRef.current
    ) {
      return;
    }
    lastToastMessageRef.current = error.message;
    toast.error(error.message);
  }, [error]);

  const requestClose = useCallback(async () => {
    if (isClosing || resetInProgressRef.current) return;
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
    if (!pendingLayoutReset || resetInProgressRef.current) return;
    resetInProgressRef.current = true;
    const orientation = pendingLayoutReset;
    setPendingLayoutReset(null);
    setResetProgress({
      percent: 0,
      label: t("admin.organizations.designer.resetProgressPreparing"),
    });

    try {
      const fullOrganizations = await fetchCompleteOrganizationTree();
      setResetProgress({
        percent: 20,
        label: t("admin.organizations.designer.resetProgressFetched"),
      });

      const fetchedOrganizationIds = flattenOrganizations(
        fullOrganizations
      ).map(({ id }) => id);
      const nextPositions = organizationTreeToLayoutPositions(
        fullOrganizations,
        orientation,
        expandedNodeIds,
        collapsedNodeIds,
        true
      );
      setResetProgress({
        percent: 45,
        label: t("admin.organizations.designer.resetProgressCalculated"),
      });

      const validationError = validateCompleteReset(
        fetchedOrganizationIds,
        writableOrganizationIds
      );
      if (validationError) {
        toast.error(
          t(
            validationError === "too-large"
              ? "admin.organizations.designer.resetTooLarge"
              : "admin.organizations.designer.resetIncompleteAccess"
          )
        );
        return;
      }

      const saved = await replacePositionsAndSave(nextPositions);
      if (!saved) {
        toast.error(t("admin.organizations.designer.resetSaveFailed"));
        return;
      }
      setResetProgress({
        percent: 75,
        label: t("admin.organizations.designer.resetProgressSaved"),
      });

      await commitResetPositions(nextPositions);

      setResetProgress({
        percent: 100,
        label: t("admin.organizations.designer.resetProgressComplete"),
      });
      await wait(COMPLETED_RESET_PROGRESS_VISIBLE_MS);
      toast.success(t("admin.organizations.designer.resetSuccess"));
    } catch (caughtError) {
      toast.error(
        caughtError instanceof Error &&
          caughtError.message === COMPLETE_TREE_FETCH_ERROR
          ? t("admin.organizations.designer.resetFetchFailed")
          : t("admin.organizations.designer.saveFailed")
      );
    } finally {
      resetInProgressRef.current = false;
      setResetProgress(null);
    }
  }, [
    collapsedNodeIds,
    commitResetPositions,
    expandedNodeIds,
    pendingLayoutReset,
    replacePositionsAndSave,
    t,
    writableOrganizationIds,
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
            <OrganizationSearchCombobox
              className={cn("ml-auto w-full max-w-md max-md:max-w-xs")}
              query={searchQuery}
              activeIndex={activeSearchMatchIndex}
              results={searchResults}
              loading={searchLoading}
              error={searchError}
              limited={resultsLimited}
              revealLoading={revealLoading}
              onQueryChange={setSearchQuery}
              onActiveIndexChange={setActiveSearchMatchIndex}
              onSearch={onSearch}
              onReveal={onRevealResult}
            />
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
                disabled={isClosing || Boolean(resetProgress)}
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
                colorMode={resolvedTheme === "dark" ? "dark" : "light"}
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
                className={cn(
                  // Animate a node's own position change (e.g. siblings
                  // reflowing when a subtree expands/collapses) so the
                  // rearrangement reads as a slide instead of a jump. Skip
                  // while the user is actively dragging so drag stays 1:1
                  // with the pointer.
                  "[&_.react-flow\_\_node]:transition-transform [&_.react-flow\_\_node]:duration-300 [&_.react-flow\_\_node]:ease-in-out motion-reduce:[&_.react-flow\_\_node]:transition-none",
                  "[&_.react-flow\_\_node.dragging]:transition-none",
                  "[&_.react-flow\_\_edge-path]:transition-[opacity,stroke] [&_.react-flow\_\_edge-path]:duration-200 motion-reduce:[&_.react-flow\_\_edge-path]:transition-none"
                )}
              >
                <Background color="var(--border-01)" gap={24} size={1} />
                <Controls
                  showInteractive={false}
                  className={cn(
                    "!border !border-border-02 !bg-background-neutral-00 !shadow-md !rounded-12 !overflow-hidden",
                    "[&_.react-flow\_\_controls-button]:!bg-background-neutral-00",
                    "[&_.react-flow\_\_controls-button]:!border-border-02",
                    "[&_.react-flow\_\_controls-button]:!text-text-04",
                    "[&_.react-flow\_\_controls-button:hover]:!bg-background-neutral-02",
                    "[&_.react-flow\_\_controls-button:hover]:!text-text-05",
                    "[&_.react-flow\_\_controls-button_svg]:!fill-current"
                  )}
                />
                <MiniMap
                  pannable
                  zoomable
                  className={cn(
                    "!rounded-12 !border !border-border-02 !bg-background-neutral-00 !shadow-md !overflow-hidden"
                  )}
                  nodeColor="var(--background-neutral-04)"
                  maskColor="color-mix(in srgb, var(--background-neutral-01) 75%, transparent)"
                  maskStrokeColor="var(--border-02)"
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
                    disabled={status === "saving" || Boolean(resetProgress)}
                    icon={SvgArrowUpDown}
                    tertiary
                    tooltip={t("admin.organizations.designer.resetVertical")}
                    onClick={() => setPendingLayoutReset("vertical")}
                  />
                  <IconButton
                    aria-label={t(
                      "admin.organizations.designer.resetHorizontal"
                    )}
                    disabled={status === "saving" || Boolean(resetProgress)}
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
          {resetProgress && (
            <ConfirmationModalLayout
              icon={SvgOrganization}
              title={t("admin.organizations.designer.resetProgressTitle")}
              hideCancel
              submit={null}
              onClose={() => {}}
            >
              <div
                data-testid="reset-progress-content"
                className={cn("flex w-full flex-col gap-3 py-2")}
              >
                <Text mainUiBody text04>
                  {resetProgress.label}
                </Text>
                <div
                  role="progressbar"
                  aria-label={resetProgress.label}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={resetProgress.percent}
                  className={cn(
                    "h-2.5 w-full overflow-hidden rounded-full bg-background-neutral-03"
                  )}
                >
                  <div
                    className={cn(
                      "h-full rounded-full bg-action-link-05 transition-all duration-300 ease-out"
                    )}
                    style={{ width: `${resetProgress.percent}%` }}
                  />
                </div>
                <Text secondaryMono text03 className={cn("text-right")}>
                  {resetProgress.percent}%
                </Text>
              </div>
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
