import type { Edge, Node, XYPosition } from "@xyflow/react";
import type { OrganizationMember } from "@/components/organization/organizationTypes";

export interface OrganizationTreeNode {
  id: string;
  name: string;
  path: string;
  parent_id: string | null;
  children?: OrganizationTreeNode[];
}

export interface OrganizationFlowNodeData extends Record<string, unknown> {
  organizationId: string;
  name: string;
  path: string;
  childCount: number;
  hasChildren?: boolean;
  isSubtreeExpanded?: boolean;
  onToggleSubtree?: () => void;
  readOnly: boolean;
  canAddChild?: boolean;
  canManage?: boolean;
  actionMode?: "rename" | "delete";
  isDraft?: boolean;
  searchMatch?: boolean;
  searchDimmed?: boolean;
  parentId?: string | null;
  parentOptions?: Array<{ id: string; name: string }>;
  onRequestMove?: (parentId: string) => void;
  isDropTarget?: boolean;
  layoutOrientation?: OrganizationLayoutOrientation;
  onAddChild?: () => void;
  onBeginDelete?: () => void;
  onBeginRename?: () => void;
  onCancelAction?: () => void;
  onCancelDraft?: () => void;
  onDelete?: () => Promise<void>;
  onRename?: (name: string) => Promise<void>;
  onSubmitDraft?: (name: string) => Promise<void>;
  members?: OrganizationMember[];
}

export type OrganizationFlowNode = Node<
  OrganizationFlowNodeData,
  "organization"
>;
export type OrganizationFlowEdge = Edge<{ active: boolean }>;
export type OrganizationPositionMap = Record<string, XYPosition>;

const ROOT_GAP = 360;
const SIBLING_GAP = 280;
const LEVEL_GAP = 180;
const HORIZONTAL_LEVEL_GAP = 360;
const HORIZONTAL_SIBLING_GAP = 180;

export type OrganizationLayoutOrientation = "vertical" | "horizontal";

interface OrganizationGraph {
  nodes: OrganizationFlowNode[];
  edges: OrganizationFlowEdge[];
}

export function isNodeSubtreeExpanded(
  nodeId: string,
  childrenLength: number,
  expandedNodeIds = new Set<string>(),
  collapsedNodeIds = new Set<string>()
): boolean {
  if (collapsedNodeIds.has(nodeId)) return false;
  if (expandedNodeIds.has(nodeId)) return true;
  return childrenLength > 0;
}

export function organizationTreeToLayoutPositions(
  organizations: OrganizationTreeNode[],
  orientation: OrganizationLayoutOrientation,
  expandedNodeIds = new Set<string>(),
  collapsedNodeIds = new Set<string>(),
  allNodes = false
): OrganizationPositionMap {
  const positions: OrganizationPositionMap = {};
  const vertical = orientation === "vertical";
  const siblingGap = vertical ? SIBLING_GAP : HORIZONTAL_SIBLING_GAP;
  const levelGap = vertical ? LEVEL_GAP : HORIZONTAL_LEVEL_GAP;

  interface LayoutNode {
    id: string;
    x: number;
    depth: number;
    width: number;
    children: { node: LayoutNode; leftOffset: number }[];
  }

  function buildSubtree(
    organization: OrganizationTreeNode,
    depth: number
  ): LayoutNode {
    const isExpanded =
      allNodes ||
      isNodeSubtreeExpanded(
        organization.id,
        (organization.children ?? []).length,
        expandedNodeIds,
        collapsedNodeIds
      );
    const rawChildren = isExpanded ? organization.children ?? [] : [];

    if (rawChildren.length === 0) {
      return {
        id: organization.id,
        x: siblingGap / 2,
        depth,
        width: siblingGap,
        children: [],
      };
    }

    let currentX = 0;
    const childrenWithOffsets: { node: LayoutNode; leftOffset: number }[] = [];

    rawChildren.forEach((child) => {
      const childLayout = buildSubtree(child, depth + 1);
      childrenWithOffsets.push({ node: childLayout, leftOffset: currentX });
      currentX += childLayout.width;
    });

    const firstChild = childrenWithOffsets[0]!;
    const lastChild = childrenWithOffsets[childrenWithOffsets.length - 1]!;
    const firstChildCenter = firstChild.leftOffset + firstChild.node.x;
    const lastChildCenter = lastChild.leftOffset + lastChild.node.x;
    const parentX = (firstChildCenter + lastChildCenter) / 2;

    return {
      id: organization.id,
      x: parentX,
      depth,
      width: Math.max(siblingGap, currentX),
      children: childrenWithOffsets,
    };
  }

  function assignCoordinates(layoutNode: LayoutNode, leftX: number): void {
    const absX = leftX + layoutNode.x;
    positions[layoutNode.id] = vertical
      ? { x: absX, y: layoutNode.depth * levelGap }
      : { x: layoutNode.depth * levelGap, y: absX };

    layoutNode.children.forEach(({ node: child, leftOffset }) => {
      assignCoordinates(child, leftX + leftOffset);
    });
  }

  let rootCursor = 0;
  organizations.forEach((organization, rootIndex) => {
    if (rootIndex > 0) {
      rootCursor += Math.max(ROOT_GAP, siblingGap);
    }
    const layoutNode = buildSubtree(organization, 0);
    assignCoordinates(layoutNode, rootCursor);
    rootCursor += layoutNode.width;
  });

  return positions;
}

export function inferOrganizationLayoutOrientation(
  organizations: OrganizationTreeNode[],
  positions: OrganizationPositionMap
): OrganizationLayoutOrientation {
  const horizontalSteps: number[] = [];
  const verticalSteps: number[] = [];

  function visit(organization: OrganizationTreeNode) {
    const parentPosition = positions[organization.id];
    for (const child of organization.children ?? []) {
      const childPosition = positions[child.id];
      if (parentPosition && childPosition) {
        horizontalSteps.push(childPosition.x - parentPosition.x);
        verticalSteps.push(childPosition.y - parentPosition.y);
      }
      visit(child);
    }
  }

  organizations.forEach(visit);
  if (horizontalSteps.length === 0) return "vertical";

  function axisConsistency(steps: number[]) {
    const sorted = [...steps].sort((first, second) => first - second);
    const median = sorted[Math.floor(sorted.length / 2)] ?? 0;
    const range = (sorted[sorted.length - 1] ?? 0) - (sorted[0] ?? 0);
    return {
      score: range / Math.max(Math.abs(median), 1),
      step: Math.abs(median),
    };
  }

  const horizontal = axisConsistency(horizontalSteps);
  const vertical = axisConsistency(verticalSteps);
  if (horizontal.score !== vertical.score) {
    return horizontal.score < vertical.score ? "horizontal" : "vertical";
  }
  return horizontal.step > vertical.step ? "horizontal" : "vertical";
}

export function repositionOrganizationSubtree(
  organizations: OrganizationTreeNode[],
  positions: OrganizationPositionMap,
  organizationId: string,
  newParentId: string,
  orientation: OrganizationLayoutOrientation
): OrganizationPositionMap {
  function findOrganization(
    nodes: OrganizationTreeNode[],
    targetId: string
  ): OrganizationTreeNode | undefined {
    for (const organization of nodes) {
      if (organization.id === targetId) return organization;
      const descendant = findOrganization(
        organization.children ?? [],
        targetId
      );
      if (descendant) return descendant;
    }
    return undefined;
  }
  const movedOrganization = findOrganization(organizations, organizationId);

  const movedPosition = positions[organizationId];
  const parentPosition = positions[newParentId];
  if (!movedOrganization || !movedPosition || !parentPosition) return {};

  const subtreeIds = new Set<string>();
  function collectSubtree(organization: OrganizationTreeNode) {
    subtreeIds.add(organization.id);
    (organization.children ?? []).forEach(collectSubtree);
  }
  collectSubtree(movedOrganization);

  const vertical = orientation === "vertical";
  const levelGap = vertical ? LEVEL_GAP : HORIZONTAL_LEVEL_GAP;
  const siblingGap = vertical ? SIBLING_GAP : HORIZONTAL_SIBLING_GAP;
  const targetLevel =
    (vertical ? parentPosition.y : parentPosition.x) + levelGap;
  const parentSiblingCoordinate = vertical
    ? parentPosition.x
    : parentPosition.y;
  const occupiedSiblingCoordinates = Object.entries(positions)
    .filter(([id, position]) => {
      if (subtreeIds.has(id)) return false;
      const levelCoordinate = vertical ? position.y : position.x;
      return Math.abs(levelCoordinate - targetLevel) < levelGap / 2;
    })
    .map(([, position]) => (vertical ? position.x : position.y));

  let slotOffset = 0;
  for (
    let distance = 0;
    distance <= occupiedSiblingCoordinates.length;
    distance += 1
  ) {
    const offsets = distance === 0 ? [0] : [distance, -distance];
    const availableOffset = offsets.find((offset) => {
      const candidate = parentSiblingCoordinate + offset * siblingGap;
      return occupiedSiblingCoordinates.every(
        (occupied) => Math.abs(occupied - candidate) >= siblingGap * 0.8
      );
    });
    if (availableOffset !== undefined) {
      slotOffset = availableOffset;
      break;
    }
  }

  const targetPosition = vertical
    ? {
        x: parentSiblingCoordinate + slotOffset * siblingGap,
        y: targetLevel,
      }
    : {
        x: targetLevel,
        y: parentSiblingCoordinate + slotOffset * siblingGap,
      };
  const delta = {
    x: targetPosition.x - movedPosition.x,
    y: targetPosition.y - movedPosition.y,
  };

  return Object.fromEntries(
    Array.from(subtreeIds)
      .filter((id) => positions[id])
      .map((id) => [
        id,
        {
          x: positions[id]!.x + delta.x,
          y: positions[id]!.y + delta.y,
        },
      ])
  );
}

function isOnSelectedPath(
  organization: OrganizationTreeNode,
  selectedOrganizationId: string | undefined
): boolean {
  if (!selectedOrganizationId) return false;
  if (organization.id === selectedOrganizationId) return true;
  return (organization.children ?? []).some((child) =>
    isOnSelectedPath(child, selectedOrganizationId)
  );
}

export function organizationTreeToFlowGraph(
  organizations: OrganizationTreeNode[],
  savedPositions: OrganizationPositionMap = {},
  writableOrganizationIds = new Set<string>(),
  selectedOrganizationId?: string,
  layoutOrientation = inferOrganizationLayoutOrientation(
    organizations,
    savedPositions
  ),
  expandedNodeIds = new Set<string>(),
  collapsedNodeIds = new Set<string>()
): OrganizationGraph {
  const nodes: OrganizationFlowNode[] = [];
  const edges: OrganizationFlowEdge[] = [];
  const fallbackPositions = organizationTreeToLayoutPositions(
    organizations,
    layoutOrientation,
    expandedNodeIds,
    collapsedNodeIds
  );

  /**
   * Visit a node and determine its canvas position.
   *
   * `parentDelta` is the translation vector between the nearest ancestor's
   * saved (actual) position and its computed fallback position.  Children
   * without their own saved position inherit this delta so the whole subtree
   * branch is translated together, preserving the tree shape while aligning
   * it under the ancestor's real location on the canvas.
   */
  function visit(
    organization: OrganizationTreeNode,
    parentDelta: XYPosition = { x: 0, y: 0 }
  ) {
    const fallbackPosition = fallbackPositions[organization.id]!;
    let position: XYPosition;
    let delta: XYPosition;

    if (savedPositions[organization.id]) {
      position = savedPositions[organization.id]!;
      delta = {
        x: position.x - fallbackPosition.x,
        y: position.y - fallbackPosition.y,
      };
    } else {
      position = {
        x: fallbackPosition.x + parentDelta.x,
        y: fallbackPosition.y + parentDelta.y,
      };
      delta = parentDelta;
    }

    const children = organization.children ?? [];
    const childCount =
      children.length > 0
        ? children.length
        : (organization as { children_count?: number }).children_count ?? 0;
    const hasChildren =
      childCount > 0 || (organization as { has_children?: boolean }).has_children === true;
    const isSubtreeExpanded = isNodeSubtreeExpanded(
      organization.id,
      children.length,
      expandedNodeIds,
      collapsedNodeIds
    );

    nodes.push({
      id: organization.id,
      type: "organization",
      position,
      selectable: true,
      draggable: writableOrganizationIds.has(organization.id),
      data: {
        organizationId: organization.id,
        name: organization.name,
        path: organization.path,
        childCount,
        hasChildren,
        isSubtreeExpanded,
        parentId: organization.parent_id,
        readOnly: !writableOrganizationIds.has(organization.id),
        layoutOrientation,
      },
      selected: organization.id === selectedOrganizationId,
    });

    if (isSubtreeExpanded) {
      children.forEach((child) => {
        const active = isOnSelectedPath(child, selectedOrganizationId);
        edges.push({
          id: `${organization.id}-${child.id}`,
          source: organization.id,
          target: child.id,
          sourceHandle: layoutOrientation === "horizontal" ? "right" : "bottom",
          targetHandle: layoutOrientation === "horizontal" ? "left" : "top",
          type: "smoothstep",
          selectable: false,
          focusable: false,
          data: { active },
          style: active
            ? { stroke: "var(--action-link-05)", strokeWidth: 2 }
            : { stroke: "var(--border-02)", strokeWidth: 1 },
        });
        visit(child, delta);
      });
    }
  }

  organizations.forEach((org) => visit(org));

  return { nodes, edges };
}
