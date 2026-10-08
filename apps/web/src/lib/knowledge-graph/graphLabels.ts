/** A node label that may be drawn, anchored at its center and text baseline. */
export interface LabelCandidate {
  id: string;
  x: number;
  baseline: number;
  text: string;
  fontSize: number;
  /** Higher draws first and wins space from lower. */
  priority: number;
}

export interface CanvasBounds {
  width: number;
  height: number;
}

// Average glyph advance of the UI font, in ems; an estimate is enough to
// keep labels apart without measuring text in the DOM.
const CHAR_WIDTH_EM = 0.58;
const PADDING = 2;

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

function boxOf(candidate: LabelCandidate): Box {
  const { fontSize } = candidate;
  const halfWidth =
    (candidate.text.length * fontSize * CHAR_WIDTH_EM) / 2 + PADDING;
  return {
    left: candidate.x - halfWidth,
    right: candidate.x + halfWidth,
    top: candidate.baseline - fontSize - PADDING,
    bottom: candidate.baseline + fontSize * 0.25 + PADDING,
  };
}

function overlaps(a: Box, b: Box): boolean {
  return (
    a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
  );
}

function outside(box: Box, bounds: CanvasBounds): boolean {
  return (
    box.right < 0 ||
    box.left > bounds.width ||
    box.bottom < 0 ||
    box.top > bounds.height
  );
}

/**
 * Labels that fit on the canvas: highest priority first, each skipped when it
 * would overlap one already placed or lies off-canvas.
 */
export function placeLabels(
  candidates: readonly LabelCandidate[],
  bounds: CanvasBounds
): Set<string> {
  const placed: Box[] = [];
  const visible = new Set<string>();
  const ordered = [...candidates].sort((a, b) => b.priority - a.priority);
  for (const candidate of ordered) {
    const box = boxOf(candidate);
    if (outside(box, bounds)) continue;
    if (placed.some((other) => overlaps(box, other))) continue;
    placed.push(box);
    visible.add(candidate.id);
  }
  return visible;
}

/** Who wins label space when labels would collide. */
export const LABEL_PRIORITY = {
  selectedNode: 5,
  selectedEdge: 4,
  neighbor: 3,
  matched: 2,
  node: 1,
  edge: 0.5,
} as const;

/** Breaks ties among matched nodes by score, never crossing a tier. */
function scoreTieBreak(score: number | null | undefined): number {
  return Math.min(Math.max(score ?? 0, 0), 1) * 0.99;
}

export function nodeLabelPriority(
  node: { id: string; matched: boolean; score?: number | null },
  selectedNodeId: string | null,
  neighbors: ReadonlySet<string>
): number {
  if (node.id === selectedNodeId) return LABEL_PRIORITY.selectedNode;
  if (neighbors.has(node.id)) return LABEL_PRIORITY.neighbor;
  if (node.matched) return LABEL_PRIORITY.matched + scoreTieBreak(node.score);
  return LABEL_PRIORITY.node;
}

/** Neighbors that did not match are named only once the user zooms in. */
export const NEIGHBOR_LABEL_ZOOM = 1.4;

export interface NodeLabelVisibility {
  matched: boolean;
  /** The node is the selection or one of its direct neighbors. */
  inFocus: boolean;
  hasSelection: boolean;
  /** Current canvas zoom factor. */
  scale: number;
}

/**
 * Whether a node is a label candidate at all (culling before collisions):
 * a selection narrows labels to its neighborhood, otherwise matched nodes are
 * always named and the rest only when zoomed in.
 */
export function isNodeLabeled({
  matched,
  inFocus,
  hasSelection,
  scale,
}: NodeLabelVisibility): boolean {
  if (hasSelection && !inFocus) return false;
  return matched || inFocus || scale >= NEIGHBOR_LABEL_ZOOM;
}
