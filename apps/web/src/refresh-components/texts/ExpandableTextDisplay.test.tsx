import {
  clampStreamingSnapOffset,
  MAX_SNAP_GAP_PX,
} from "./ExpandableTextDisplay";

describe("clampStreamingSnapOffset", () => {
  it("keeps a snap that only nudges past a short block", () => {
    // Snapping past a 4px overhang of a paragraph is harmless.
    expect(clampStreamingSnapOffset(144, 140)).toBe(144);
  });

  it("clamps a snap that would hoist a tall code block fully out of view", () => {
    // rawOverflow 208, code-fence bottom 400: snapping there leaves only a
    // one-line sliver of the block background visible (the reported bug).
    expect(clampStreamingSnapOffset(400, 208)).toBe(208 + MAX_SNAP_GAP_PX);
  });

  it("never shifts less than the raw overflow so the newest text stays pinned", () => {
    expect(clampStreamingSnapOffset(120, 208)).toBe(208);
  });

  it("falls back to the raw overflow for a non-finite snap", () => {
    expect(clampStreamingSnapOffset(Number.NaN, 96)).toBe(96);
  });
});
