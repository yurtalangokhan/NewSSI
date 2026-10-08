import { PAL, paletteFor } from "./palette";
import type { TurksatCompany, TurksatMode } from "./types";

const COMPANIES: TurksatCompany[] = ["bilisim", "uydu", "kablo"];
const MODES: TurksatMode[] = ["light", "dark"];

describe("palettes", () => {
  // `hexA` parses `#rrggbb` only; a shorthand or named color would silently
  // become NaN channels at draw time instead of failing loudly.
  describe.each(COMPANIES)("%s", (company) => {
    it.each(MODES)("declares only #rrggbb tokens in %s mode", (mode) => {
      for (const [token, value] of Object.entries(PAL[company][mode])) {
        expect({ token, value }).toEqual({
          token,
          value: expect.stringMatching(/^#[0-9A-Fa-f]{6}$/),
        });
      }
    });

    it("gives light and dark the same token set", () => {
      expect(Object.keys(PAL[company].dark).sort()).toEqual(
        Object.keys(PAL[company].light).sort()
      );
    });
  });

  describe("paletteFor", () => {
    it.each(COMPANIES)("returns the light palette for %s", (company) => {
      expect(paletteFor(company, false)).toBe(PAL[company].light);
    });

    it.each(COMPANIES)("returns the dark palette for %s", (company) => {
      expect(paletteFor(company, true)).toBe(PAL[company].dark);
    });
  });
});
