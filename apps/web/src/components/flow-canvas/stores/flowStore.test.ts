/**
 * `paletteHoverOrigin` round-trip — the store field `TemplateNode`'s
 * `dragOrigin` reads to glow canvas handles while a palette item is hovered
 * (design spec: flow-canvas-connect-ux, decision 2/3). No existing
 * `flowStore.test.ts` covered the chrome slice before this; scoped to the
 * new field only, not a general store-coverage backfill.
 */

import { createFlowStore } from "./flowStore";

describe("flowStore — paletteHoverOrigin", () => {
  it("defaults to null", () => {
    const store = createFlowStore();
    expect(store.getState().paletteHoverOrigin).toBeNull();
  });

  it("sets and clears the hovered palette origin", () => {
    const store = createFlowStore();

    store.getState().setPaletteHoverOrigin({
      types: ["Model"],
      handleType: "source",
    });
    expect(store.getState().paletteHoverOrigin).toEqual({
      types: ["Model"],
      handleType: "source",
    });

    store.getState().setPaletteHoverOrigin(null);
    expect(store.getState().paletteHoverOrigin).toBeNull();
  });
});
