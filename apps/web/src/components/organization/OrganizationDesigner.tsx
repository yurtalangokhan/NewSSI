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
  type OnInit,
  type OnNodeDrag,
} from "@xyflow/react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { useTheme } from "next-themes";
import "@xyflow/react/dist/style.css";

import { OrganizationDesignerInspector } from "@/components/organization/OrganizationDesignerInspector";
import {
  getProgressiveCollapsedIds,
  getProgressiveLayoutPositions,
} from "@/components/organization/organizationProgressiveTree";
import { OrganizationMiniMapNode } from "@/components/organization/OrganizationMiniMapNode";
import { getOrganizationMinZoom } from "@/components/organization/organizationViewport";
import { OrganizationFlowNode } from "@/components/organization/OrganizationFlowNode";
import { OrganizationMoveConfirmationModal } from "@/components/organization/OrganizationMoveConfirmationModal";
import { OrganizationSearchCombobox } from "@/components/organization/OrganizationSearchCombobox";
import {
  organizationTreeToFlowGraph,
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
  SvgExpand,
  SvgOrganization,
  SvgX,
  SvgLayoutVertical,
  SvgLayoutHorizontal,
} from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationDesignerProps extends Partial<OrganizationSearchProps> {
  organizations: OrganizationNode[];
  selectedOrg: OrganizationNode | null;
  members: OrganizationMember[];
  editable: boolean;
  capabilityLoading: boolean;
  /** Viewer's organization scope; gates role escalation in the users panel. */
  globalAccess: boolean;
  canCreateRoot: boolean;
  canMoveOrganization: boolean;
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
const NODE_CLOSE_ANIMATION_MS = 200;

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
  globalAccess,
  canCreateRoot,
  canMoveOrganization,
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
  const [layoutOrientation, setLayoutOrientation] =
    useState<OrganizationLayoutOrientation>("vertical");
  const flowInstanceRef = useRef<
    Parameters<OnInit<OrganizationCanvasNode, OrganizationFlowEdge>>[0] | null
  >(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const completedRevealIdRef = useRef<number | null>(null);
  const draggingNodeIdRef = useRef<string | null>(null);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(
    Boolean(selectedOrg)
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(-1);
  const [pendingMove, setPendingMove] = useState<{
    organization: OrganizationNode;
    parent: OrganizationNode;
  } | null>(null);
  const [orientationFitPending, setOrientationFitPending] = useState(false);
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
  const visibleCollapsedIds = useMemo(
    () =>
      getProgressiveCollapsedIds(
        organizations,
        expandedNodeIds,
        collapsedNodeIds
      ),
    [organizations, expandedNodeIds, collapsedNodeIds]
  );
  const [branchToFocus, setBranchToFocus] = useState<string | null>(null);
  // Subtree roots mid-collapse: their children stay mounted (fading out via
  // CSS) until the timeout below actually removes them from the graph, so
  // the collapse reads as a transition instead of an instant disappearance.
  const [closingNodeIds, setClosingNodeIds] = useState<Set<string>>(
    () => new Set()
  );
  const closeTimeoutsRef = useRef(
    new Map<string, ReturnType<typeof setTimeout>>()
  );

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
        visibleCollapsedIds
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
        setBranchToFocus(nodeId);
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
    [visibleCollapsedIds, expandedNodeIds, onExpandOrg]
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
    () =>
      canMoveOrganization
        ? new Set(organizationsById.keys())
        : new Set<string>(),
    [canMoveOrganization, organizationsById]
  );
  const baseGraph = useMemo(
    () =>
      organizationTreeToFlowGraph(
        organizations,
        getProgressiveLayoutPositions(
          organizations,
          layoutOrientation,
          expandedNodeIds,
          visibleCollapsedIds,
          showMembers
        ),
        canvasWritableOrganizationIds,
        selectedOrg?.id,
        layoutOrientation,
        expandedNodeIds,
        visibleCollapsedIds
      ),
    [
      canvasWritableOrganizationIds,
      showMembers,
      visibleCollapsedIds,
      expandedNodeIds,
      layoutOrientation,
      organizations,
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
    const nodes: OrganizationCanvasNode[] = baseGraph.nodes.map((node) => {
      const source = organizationsById.get(node.id);
      const excludedParentIds = source
        ? descendantIds(source)
        : new Set<string>();
      return {
        ...node,
        draggable: Boolean(node.draggable && !source?.is_scope_root),
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
          members: showMembers ? membersByOrganizationId[node.id] ?? [] : [],
          parentOptions: allOrganizations
            .filter((candidate) => {
              return (
                source &&
                candidate.id !== node.id &&
                !excludedParentIds.has(candidate.id)
              );
            })
            .map(({ id, name }) => ({ id, name })),
          onRequestMove: (parentId: string) => {
            const organization = organizationsById.get(node.id);
            const parent = organizationsById.get(parentId);
            if (
              canMoveOrganization &&
              organization &&
              !organization.is_scope_root &&
              parent &&
              organization.parent_id !== parent.id
            )
              setPendingMove({ organization, parent });
          },
          canAddChild:
            node.id === selectedOrg?.id && editable && !capabilityLoading,
          canManage:
            node.id === selectedOrg?.id && editable && !capabilityLoading,
          canDelete: !organizationsById.get(node.id)?.is_scope_root,
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
      };
    });
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
    canMoveOrganization,
    closingDescendantIds,
    draftParentId,
    editable,
    allOrganizations,
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
  const minZoom = useMemo(() => getOrganizationMinZoom(nodes), [nodes]);
  const initialViewportReadyRef = useRef(false);
  const focusRoot = useCallback(() => {
    const root = nodes.find((node) => node.id === organizations[0]?.id);
    if (!root) return;
    void flowInstanceRef.current?.fitView({
      nodes: nodes.filter(
        (node) => node.id === root.id || node.data.parentId === root.id
      ),
      padding: 0.5,
      minZoom: 0.1,
      maxZoom: 1,
      duration: 300,
    });
  }, [nodes, organizations]);

  useEffect(() => {
    if (initialViewportReadyRef.current || !nodesInitialized || !nodes.length)
      return;
    // Wait for the calculated graph to commit before choosing the viewport.
    if (
      nodes.length !== graph.nodes.length ||
      nodes.some((node, index) => {
        const expected = graph.nodes[index];
        return (
          node.id !== expected?.id ||
          node.position.x !== expected.position.x ||
          node.position.y !== expected.position.y
        );
      })
    )
      return;
    initialViewportReadyRef.current = true;
    if (!revealRequest && !orientationFitPending) focusRoot();
  }, [
    focusRoot,
    graph.nodes,
    minZoom,
    nodes,
    nodesInitialized,
    orientationFitPending,
    revealRequest,
  ]);

  useEffect(() => {
    if (!draggingNodeIdRef.current) {
      setNodes(graph.nodes);
      return;
    }
    setNodes((current) =>
      graph.nodes.map((node) => {
        const dragged =
          draggingNodeIdRef.current === node.id
            ? current.find((candidate) => candidate.id === node.id)
            : undefined;
        return dragged ? { ...node, position: dragged.position } : node;
      })
    );
  }, [graph.nodes, setNodes]);

  useEffect(() => {
    if (!branchToFocus || !nodesInitialized) return;
    if (revealRequest && completedRevealIdRef.current !== revealRequest.id)
      return;
    const expected = graph.nodes.filter(
      (node) =>
        node.id === branchToFocus || node.data.parentId === branchToFocus
    );
    if (expected.length < 2) return;
    const actual = new Map(nodes.map((node) => [node.id, node]));
    if (
      expected.some(
        (node) =>
          actual.get(node.id)?.position.x !== node.position.x ||
          actual.get(node.id)?.position.y !== node.position.y
      )
    )
      return;
    setBranchToFocus(null);
    void flowInstanceRef.current?.fitView({
      nodes: expected,
      padding: 0.3,
      minZoom: 0.15,
      maxZoom: 1,
      duration: 300,
    });
  }, [branchToFocus, graph.nodes, nodes, nodesInitialized, revealRequest]);

  useEffect(() => {
    if (!orientationFitPending || !nodesInitialized) return;
    if (
      nodes.length !== graph.nodes.length ||
      nodes.some((node, index) => {
        const expected = graph.nodes[index];
        return (
          node.id !== expected?.id ||
          node.position.x !== expected.position.x ||
          node.position.y !== expected.position.y
        );
      })
    )
      return;
    setOrientationFitPending(false);
    void flowInstanceRef.current?.fitView({
      nodes,
      minZoom,
      padding: 0.2,
      duration: 300,
    });
  }, [orientationFitPending, nodesInitialized, nodes, graph.nodes, minZoom]);

  useEffect(() => {
    if (!revealRequest || completedRevealIdRef.current === revealRequest.id) {
      return;
    }
    setBranchToFocus(null);
    const pathIds = new Set(revealRequest.ancestorIds);
    setExpandedNodeIds(pathIds);
    setCollapsedNodeIds(
      new Set(
        allOrganizations
          .filter((node) => !pathIds.has(node.id))
          .map((node) => node.id)
      )
    );
  }, [revealRequest, allOrganizations]);

  useEffect(() => {
    if (
      !revealRequest ||
      !nodesInitialized ||
      completedRevealIdRef.current === revealRequest.id
    ) {
      return;
    }
    const targetNode = graph.nodes.find(
      ({ id }) => id === revealRequest.result.id
    );
    if (!targetNode) return;
    const committedNode = nodes.find(({ id }) => id === targetNode.id);
    if (
      !committedNode ||
      committedNode.position.x !== targetNode.position.x ||
      committedNode.position.y !== targetNode.position.y
    )
      return;
    const instance = flowInstanceRef.current;
    if (!instance) return;
    // Graph data and React Flow measurements commit separately. Fit only once
    // the renderer knows the target's dimensions.
    if (instance.getNode) {
      const rendered = instance.getNode(targetNode.id);
      if (!rendered?.measured?.width || !rendered.measured.height) return;
    }
    const organization = organizationsById.get(revealRequest.result.id);
    if (!organization) return;
    completedRevealIdRef.current = revealRequest.id;
    onRevealReady(organization);
    setMobileInspectorOpen(true);
    void flowInstanceRef.current?.fitView({
      nodes: [targetNode],
      padding: 0.8,
      minZoom: 0.5,
      maxZoom: 1,
      duration: 300,
    });
  }, [
    graph.nodes,
    nodes,
    nodesInitialized,
    onRevealReady,
    organizationsById,
    revealRequest,
  ]);

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

  const requestClose = useCallback(() => {
    onClose();
  }, [onClose]);

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

  const handleNodesChange = useCallback(
    (changes: NodeChange<OrganizationCanvasNode>[]) => {
      onNodesChange(
        changes.filter(
          (change) =>
            change.type !== "position" ||
            (change.id === draggingNodeIdRef.current &&
              change.dragging !== undefined)
        )
      );
    },
    [onNodesChange]
  );

  const findDropTarget = useCallback(
    (node: OrganizationCanvasNode) => {
      const source = organizationsById.get(node.id);
      if (
        !source ||
        source.is_scope_root ||
        !canMoveOrganization ||
        !canvasWritableOrganizationIds.has(node.id)
      )
        return;
      const descendants = descendantIds(source);
      return flowInstanceRef.current
        ?.getIntersectingNodes(node)
        .map((candidate) => organizationsById.get(candidate.id))
        .find(
          (target) =>
            target &&
            target.id !== source.id &&
            target.id !== source.parent_id &&
            !descendants.has(target.id) &&
            canvasWritableOrganizationIds.has(target.id)
        );
    },
    [canMoveOrganization, organizationsById, canvasWritableOrganizationIds]
  );

  const handleNodeDragStart: OnNodeDrag<OrganizationCanvasNode> = useCallback(
    (_, node) => {
      if (node.draggable) {
        draggingNodeIdRef.current = node.id;
        setBranchToFocus(null);
      }
    },
    []
  );

  const handleNodeDrag: OnNodeDrag<OrganizationCanvasNode> = useCallback(
    (_, node) => {
      if (draggingNodeIdRef.current !== node.id) return;
      const target = findDropTarget(node);
      setNodes((current) =>
        current.map((candidate) => ({
          ...candidate,
          data: {
            ...candidate.data,
            isDropTarget: candidate.id === target?.id,
          },
        }))
      );
    },
    [findDropTarget, setNodes]
  );

  const handleNodeDragStop: OnNodeDrag<OrganizationCanvasNode> = useCallback(
    (_, node) => {
      if (draggingNodeIdRef.current !== node.id) return;
      const target = findDropTarget(node);
      draggingNodeIdRef.current = null;
      setNodes(graph.nodes);
      const organization = organizationsById.get(node.id);
      if (target && organization)
        setPendingMove({ organization, parent: target });
    },
    [findDropTarget, graph.nodes, organizationsById, setNodes]
  );

  const handleInit: OnInit<OrganizationCanvasNode, OrganizationFlowEdge> =
    useCallback((instance) => {
      flowInstanceRef.current = instance;
    }, []);

  const changeOrientation = useCallback(
    (orientation: OrganizationLayoutOrientation) => {
      setBranchToFocus(null);
      setLayoutOrientation(orientation);
      setOrientationFitPending(true);
    },
    []
  );

  const confirmOrganizationMove = useCallback(async () => {
    if (!pendingMove) return;
    const move = pendingMove;
    setPendingMove(null);
    const moved = await onMoveOrg(move.organization.id, move.parent.id);
    if (!moved) return;

    setExpandedNodeIds((current) => new Set(current).add(move.parent.id));
    setCollapsedNodeIds((current) => {
      const next = new Set(current);
      next.delete(move.parent.id);
      return next;
    });
    setBranchToFocus(move.parent.id);
    await onExpandOrg?.(move.parent.id);
  }, [onExpandOrg, onMoveOrg, pendingMove]);

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
              {t("admin.organizations.designer.ready")}
            </Text>
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
              <IconButton
                icon={SvgX}
                tooltip={t("admin.organizations.designer.close")}
                aria-label={t("admin.organizations.designer.close")}
                tertiary
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
                fitViewOptions={{ padding: 0.2, minZoom }}
                minZoom={minZoom}
                maxZoom={2}
                proOptions={{ hideAttribution: true }}
                onInit={handleInit}
                onNodeClick={handleNodeClick}
                onNodesChange={handleNodesChange}
                onNodeDragStart={handleNodeDragStart}
                onNodeDrag={handleNodeDrag}
                onNodeDragStop={handleNodeDragStop}
                className={cn(
                  // Animate a node's own position change (e.g. siblings
                  // reflowing when a subtree expands/collapses) so the
                  // rearrangement reads as a slide instead of a jump. Skip
                  // while the user is actively dragging so drag stays 1:1
                  // with the pointer.
                  "[&_.react-flow__node]:transition-transform [&_.react-flow__node]:duration-300 [&_.react-flow__node]:ease-in-out motion-reduce:[&_.react-flow__node]:transition-none",
                  "[&_.react-flow__node.dragging]:transition-none",
                  "[&_.react-flow__edge-path]:transition-[opacity,stroke] [&_.react-flow__edge-path]:duration-200 motion-reduce:[&_.react-flow__edge-path]:transition-none"
                )}
              >
                <Background color="var(--border-01)" gap={24} size={1} />
                <Controls
                  showInteractive={false}
                  fitViewOptions={{ padding: 0.2, minZoom }}
                  className={cn(
                    "!border !border-border-02 !bg-background-neutral-00 !shadow-md !rounded-12 !overflow-hidden",
                    "[&_.react-flow__controls-button]:!bg-background-neutral-00",
                    "[&_.react-flow__controls-button]:!border-border-02",
                    "[&_.react-flow__controls-button]:!text-text-04",
                    "[&_.react-flow__controls-button:hover]:!bg-background-neutral-02",
                    "[&_.react-flow__controls-button:hover]:!text-text-05",
                    "[&_.react-flow__controls-button_svg]:!fill-current"
                  )}
                />
                <MiniMap
                  pannable
                  zoomable
                  nodeComponent={OrganizationMiniMapNode}
                  ariaLabel={t("admin.organizations.designer.minimap")}
                  onNodeClick={(_, node) => {
                    void flowInstanceRef.current?.fitView({
                      nodes: [node],
                      padding: 0.5,
                      minZoom: 0.5,
                      maxZoom: 1,
                      duration: 300,
                    });
                  }}
                  className={cn(
                    "!rounded-12 !border !border-border-02 !bg-background-neutral-00 !shadow-md !overflow-hidden"
                  )}
                  nodeColor="var(--theme-primary-04)"
                  maskColor="color-mix(in srgb, var(--background-neutral-01) 35%, transparent)"
                  maskStrokeColor="var(--theme-primary-05)"
                  maskStrokeWidth={2}
                />
              </ReactFlow>
              <div
                className={cn(
                  "absolute right-4 top-4 z-10 flex items-center gap-2"
                )}
              >
                <div
                  className={cn(
                    "flex items-center gap-1 rounded-12 border border-border-02 bg-background-neutral-00 p-1 shadow-md"
                  )}
                >
                  <IconButton
                    icon={SvgOrganization}
                    tooltip={t("admin.organizations.designer.focusRoot")}
                    aria-label={t("admin.organizations.designer.focusRoot")}
                    tertiary
                    disabled={!nodes.length}
                    onClick={focusRoot}
                  />
                  <IconButton
                    icon={SvgExpand}
                    tooltip={t("admin.organizations.designer.fitView")}
                    aria-label={t("admin.organizations.designer.fitView")}
                    tertiary
                    onClick={() =>
                      void flowInstanceRef.current?.fitView({
                        padding: 0.2,
                        minZoom,
                      })
                    }
                  />
                </div>
                {organizations.length > 0 && (
                  <div
                    className={cn(
                      "flex items-center gap-1 rounded-12 border border-border-02 bg-background-neutral-00 p-1 shadow-md"
                    )}
                  >
                    <IconButton
                      aria-label={t(
                        "admin.organizations.designer.verticalView"
                      )}
                      icon={SvgLayoutVertical}
                      aria-pressed={layoutOrientation === "vertical"}
                      secondary={layoutOrientation === "vertical"}
                      tertiary={layoutOrientation !== "vertical"}
                      tooltip={t("admin.organizations.designer.verticalView")}
                      onClick={() => changeOrientation("vertical")}
                    />
                    <IconButton
                      aria-label={t(
                        "admin.organizations.designer.horizontalView"
                      )}
                      icon={SvgLayoutHorizontal}
                      aria-pressed={layoutOrientation === "horizontal"}
                      secondary={layoutOrientation === "horizontal"}
                      tertiary={layoutOrientation !== "horizontal"}
                      tooltip={t("admin.organizations.designer.horizontalView")}
                      onClick={() => changeOrientation("horizontal")}
                    />
                  </div>
                )}
              </div>
              {organizations.length === 0 &&
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
                  className={cn("absolute right-4 top-20 z-10 md:hidden")}
                  onClick={() => setMobileInspectorOpen(true)}
                >
                  {t("admin.organizations.designer.showInspector")}
                </Button>
              )}
            </div>

            <OrganizationDesignerInspector
              globalAccess={globalAccess}
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
