import type { Edge, Node, XYPosition } from "@xyflow/react";

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
  readOnly: boolean;
  canAddChild?: boolean;
  canManage?: boolean;
  actionMode?: "rename" | "delete";
  isDraft?: boolean;
  onAddChild?: () => void;
  onBeginDelete?: () => void;
  onBeginRename?: () => void;
  onCancelAction?: () => void;
  onCancelDraft?: () => void;
  onDelete?: () => Promise<void>;
  onRename?: (name: string) => Promise<void>;
  onSubmitDraft?: (name: string) => Promise<void>;
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

interface OrganizationGraph {
  nodes: OrganizationFlowNode[];
  edges: OrganizationFlowEdge[];
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
  selectedOrganizationId?: string
): OrganizationGraph {
  const nodes: OrganizationFlowNode[] = [];
  const edges: OrganizationFlowEdge[] = [];
  const fallbackPositions = new Map<string, XYPosition>();
  let nextLeafX = 0;

  function placeSubtree(
    organization: OrganizationTreeNode,
    depth: number
  ): number {
    const children = organization.children ?? [];
    let x: number;
    if (children.length === 0) {
      x = nextLeafX;
      nextLeafX += SIBLING_GAP;
    } else {
      const childXs = children.map((child) => placeSubtree(child, depth + 1));
      x = (childXs[0]! + childXs[childXs.length - 1]!) / 2;
    }
    fallbackPositions.set(organization.id, { x, y: depth * LEVEL_GAP });
    return x;
  }

  organizations.forEach((organization, rootIndex) => {
    if (rootIndex > 0) nextLeafX += Math.max(0, ROOT_GAP - SIBLING_GAP);
    placeSubtree(organization, 0);
  });

  function visit(organization: OrganizationTreeNode) {
    const fallbackPosition = fallbackPositions.get(organization.id)!;
    const position = savedPositions[organization.id] ?? fallbackPosition;
    const children = organization.children ?? [];

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
        childCount: children.length,
        readOnly: !writableOrganizationIds.has(organization.id),
      },
      selected: organization.id === selectedOrganizationId,
    });

    children.forEach((child) => {
      const active = isOnSelectedPath(child, selectedOrganizationId);
      edges.push({
        id: `${organization.id}-${child.id}`,
        source: organization.id,
        target: child.id,
        type: "smoothstep",
        selectable: false,
        focusable: false,
        data: { active },
        style: active
          ? { stroke: "var(--action-link-05)", strokeWidth: 2 }
          : { stroke: "var(--border-02)", strokeWidth: 1 },
      });
      visit(child);
    });
  }

  organizations.forEach(visit);

  return { nodes, edges };
}
