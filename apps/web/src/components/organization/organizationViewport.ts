interface PositionedNode {
  position: { x: number; y: number };
  measured?: { width?: number; height?: number };
}

// Keep enough zoom range to fit even a full saved tree into a narrow canvas.
// Bounds are translation-independent, so moving a compact tree far from the
// origin does not unnecessarily change its zoom limits.
export function getOrganizationMinZoom(nodes: PositionedNode[]): number {
  if (!nodes.length) return 0.2;
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const node of nodes) {
    left = Math.min(left, node.position.x);
    top = Math.min(top, node.position.y);
    right = Math.max(right, node.position.x + (node.measured?.width ?? 320));
    bottom = Math.max(bottom, node.position.y + (node.measured?.height ?? 180));
  }
  return Math.min(0.2, 160 / Math.max(right - left, bottom - top));
}
