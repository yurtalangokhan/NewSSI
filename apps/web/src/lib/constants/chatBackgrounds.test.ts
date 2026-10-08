import {
  CHAT_BACKGROUND_OPTIONS,
  getBackgroundById,
  getLockedColorMode,
  isCanvasBackground,
  isNoBackground,
} from "./chatBackgrounds";

const TURKSAT_IDS = [
  "turksat-bilisim",
  "turksat-uydu",
  "turksat-kablo",
] as const;

describe("chatBackgrounds", () => {
  it("keeps every id unique", () => {
    const ids = CHAT_BACKGROUND_OPTIONS.map((bg) => bg.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("defaults every existing photo option to image kind (no regression)", () => {
    const photoIds = ["none", "clouds", "hills", "plant", "mountains", "night"];
    for (const id of photoIds) {
      const bg = getBackgroundById(id);
      expect(bg && isCanvasBackground(bg)).toBe(false);
    }
  });

  it.each(TURKSAT_IDS)("declares %s as a canvas-kind option", (id) => {
    const bg = getBackgroundById(id);
    expect(bg && isCanvasBackground(bg)).toBe(true);
    expect(bg && isNoBackground(bg)).toBe(false);
    // A canvas scene has no image to fetch, so it carries no src/thumbnail
    // placeholder that could be mistaken for a URL.
    expect(bg).not.toHaveProperty("src");
    expect(bg).not.toHaveProperty("thumbnail");
  });

  it("declares one option per company that follows the color mode", () => {
    (["bilisim", "uydu", "kablo"] as const).forEach((company) => {
      const bg = getBackgroundById(`turksat-${company}`);
      expect(bg && isCanvasBackground(bg) && bg.canvas).toEqual({ company });
      expect(bg).not.toHaveProperty("isDarkBackground");
    });
  });

  describe("getLockedColorMode", () => {
    it("pins the color mode a fixed photo dictates", () => {
      const lockedModes = CHAT_BACKGROUND_OPTIONS.map((bg) => [
        bg.id,
        getLockedColorMode(bg),
      ]);
      expect(lockedModes).toEqual([
        ["none", null],
        ["clouds", "light"],
        ["hills", "light"],
        ["plant", "dark"],
        ["mountains", "dark"],
        ["night", "dark"],
        ["turksat-bilisim", null],
        ["turksat-uydu", null],
        ["turksat-kablo", null],
      ]);
    });
  });

  describe("isNoBackground", () => {
    it("is true for the none option and for a missing option", () => {
      expect(isNoBackground(getBackgroundById("none"))).toBe(true);
      expect(isNoBackground(undefined)).toBe(true);
    });

    it("is false for photos and canvas scenes", () => {
      expect(isNoBackground(getBackgroundById("night"))).toBe(false);
      expect(isNoBackground(getBackgroundById("turksat-kablo"))).toBe(false);
    });
  });

  it("gives every TÜRKSAT option a distinct, non-empty label", () => {
    const labels = TURKSAT_IDS.map((id) => getBackgroundById(id)?.label);
    labels.forEach((label) => expect(label).toBeTruthy());
    expect(new Set(labels).size).toBe(labels.length);
  });
});
