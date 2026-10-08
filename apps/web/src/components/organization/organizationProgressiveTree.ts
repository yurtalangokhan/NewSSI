import {
  organizationTreeToLayoutPositions,
  type OrganizationLayoutOrientation,
  type OrganizationTreeNode,
} from "@/components/organization/organizationGraph";

export function getProgressiveLayoutPositions(
  roots: OrganizationTreeNode[],
  orientation: OrganizationLayoutOrientation,
  expanded: Set<string>,
  collapsed: Set<string>,
  showMembers: boolean
) {
  const positions = organizationTreeToLayoutPositions(
    roots,
    orientation,
    expanded,
    collapsed
  );
  // Member previews add up to four rows to a card. Reserve their height in
  // vertical levels and horizontal sibling rows, without widening branches.
  if (showMembers)
    Object.values(positions).forEach((position) => {
      position.y *= 2.5;
    });
  return positions;
}

export function getProgressiveCollapsedIds(
  roots: OrganizationTreeNode[],
  expanded: Set<string>,
  collapsed: Set<string>
): Set<string> {
  const result = new Set(collapsed);
  const visit = (node: OrganizationTreeNode, depth: number) => {
    if (depth >= 1 && !expanded.has(node.id)) result.add(node.id);
    node.children?.forEach((child) => visit(child, depth + 1));
  };
  roots.forEach((root) => visit(root, 0));
  return result;
}
