import {
  NEIGHBOR_LABEL_ZOOM,
  isNodeLabeled,
  nodeLabelPriority,
  placeLabels,
  type LabelCandidate,
} from "@/lib/knowledge-graph/graphLabels";

const bounds = { width: 720, height: 470 };

function label(
  id: string,
  x: number,
  baseline: number,
  priority: number,
  text = "Multi-agent Collaboration"
): LabelCandidate {
  return { id, x, baseline, text, fontSize: 12, priority };
}

describe("placeLabels", () => {
  it("keeps only the higher-priority label where two would overlap", () => {
    const visible = placeLabels(
      [label("low", 300, 200, 1), label("high", 305, 202, 3)],
      bounds
    );

    expect(Array.from(visible)).toEqual(["high"]);
  });

  it("keeps labels that do not touch", () => {
    const visible = placeLabels(
      [label("a", 150, 100, 1), label("b", 550, 380, 1)],
      bounds
    );

    expect(visible).toEqual(new Set(["a", "b"]));
  });

  it("drops labels that fall outside the canvas", () => {
    const visible = placeLabels([label("off", -400, 100, 5)], bounds);

    expect(visible.size).toBe(0);
  });

  it("keeps input order among equal priorities", () => {
    const visible = placeLabels(
      [label("first", 300, 200, 1), label("second", 302, 200, 1)],
      bounds
    );

    expect(Array.from(visible)).toEqual(["first"]);
  });
});

describe("nodeLabelPriority", () => {
  const neighbors = new Set(["near"]);
  const node = (id: string, matched: boolean, score: number | null = null) => ({
    id,
    matched,
    score,
  });

  it("ranks selected over neighbors over matched over the rest", () => {
    const ranks = [
      nodeLabelPriority(node("sel", false), "sel", neighbors),
      nodeLabelPriority(node("near", false), "sel", neighbors),
      nodeLabelPriority(node("hit", true, 1), "sel", neighbors),
      nodeLabelPriority(node("other", false), "sel", neighbors),
    ];

    expect([...ranks].sort((a, b) => b - a)).toEqual(ranks);
  });

  it("orders matched nodes by score without leaving their tier", () => {
    const strong = nodeLabelPriority(node("a", true, 0.9), null, neighbors);
    const weak = nodeLabelPriority(node("b", true, 0.1), null, neighbors);
    const neighbor = nodeLabelPriority(node("near", false), "x", neighbors);

    expect(strong).toBeGreaterThan(weak);
    expect(neighbor).toBeGreaterThan(strong);
  });
});

describe("isNodeLabeled", () => {
  const base = { matched: false, inFocus: false, hasSelection: false };

  it("always names matched nodes when nothing is selected", () => {
    expect(isNodeLabeled({ ...base, matched: true, scale: 0.2 })).toBe(true);
  });

  it("names unmatched nodes only once the user zooms in", () => {
    expect(isNodeLabeled({ ...base, scale: NEIGHBOR_LABEL_ZOOM - 0.1 })).toBe(
      false
    );
    expect(isNodeLabeled({ ...base, scale: NEIGHBOR_LABEL_ZOOM })).toBe(true);
  });

  it("names only the selection's neighborhood while a node is selected", () => {
    const selected = { ...base, hasSelection: true, scale: 3 };

    expect(isNodeLabeled({ ...selected, matched: true })).toBe(false);
    expect(isNodeLabeled({ ...selected, inFocus: true })).toBe(true);
  });

  it("names a focused node at any zoom", () => {
    expect(
      isNodeLabeled({ ...base, hasSelection: true, inFocus: true, scale: 0.1 })
    ).toBe(true);
  });
});
