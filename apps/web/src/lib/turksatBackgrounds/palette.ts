import type { TurksatCompany, TurksatMode } from "./types";

/**
 * Per-company, per-mode color tokens. Each company has its own key set, so a
 * scene reads its palette through `paletteFor(company, env.dark)` and gets
 * its own fully-typed shape (`string`, never `string | undefined`).
 *
 * Brand-driven tokens (`accent`/cyan and `red` for Bilişim and Uydu; `fiber`
 * and `led` for Kablo) are anchored to colors sampled directly from
 * Türksat's own assets rather than invented:
 *  - `#0096D7` / `#243444`: the corporate logo (turksat_logotip_cmyk) and
 *    turksat.com.tr's own compiled CSS (`#009BDA`, `#243444`, `#5E6B77`).
 *  - `#EB2133`: turksat.com.tr's compiled CSS accent red (the current logo
 *    itself carries no red — this is a UI accent, not a logotype color).
 *  - `#359CD3` / `#76CCAC`: turksatkablonet.com's own theme color
 *    (`#2C4496`) and compiled CSS (`#359CD3` sky-blue, `#76CCAC` mint).
 * `gold` (Uydu) and `copper`/`device` (Kablo) stay representational —
 * satellite thermal-blanket foil and coaxial-cable copper are real material
 * colors, not brand colors, so they're untouched by this.
 */
export interface BilisimPalette {
  bg0: string;
  bg1: string;
  ink: string;
  accent: string;
  red: string;
  led: string;
}

export interface UyduPalette {
  sky0: string;
  sky1: string;
  bg0: string;
  ink: string;
  gold: string;
  red: string;
  ground0: string;
  ground1: string;
  dish: string;
}

export interface KabloPalette {
  bg0: string;
  bg1: string;
  ink: string;
  copper: string;
  fiber: string;
  red: string;
  device: string;
  led: string;
}

export const PAL: {
  bilisim: Record<TurksatMode, BilisimPalette>;
  uydu: Record<TurksatMode, UyduPalette>;
  kablo: Record<TurksatMode, KabloPalette>;
} = {
  bilisim: {
    light: {
      bg0: "#F4F7FC",
      bg1: "#E3EBF8",
      ink: "#243444",
      accent: "#0096D7",
      red: "#EB2133",
      led: "#149A6B",
    },
    dark: {
      bg0: "#060D1C",
      bg1: "#0E1E3C",
      ink: "#9FB7C4",
      accent: "#4DC8F5",
      red: "#FF5C6E",
      led: "#3EE0A0",
    },
  },
  uydu: {
    light: {
      sky0: "#F1F5FB",
      sky1: "#DCE6F4",
      bg0: "#E6EDF7",
      ink: "#243444",
      gold: "#A06D12",
      red: "#EB2133",
      ground0: "#B9C6DB",
      ground1: "#CBD6E6",
      dish: "#EEF2F8",
    },
    dark: {
      sky0: "#030715",
      sky1: "#0F2248",
      bg0: "#081229",
      ink: "#9FB7C4",
      gold: "#E8B350",
      red: "#FF5C6E",
      ground0: "#010309",
      ground1: "#050B1A",
      dish: "#16213D",
    },
  },
  kablo: {
    light: {
      bg0: "#F5F7FA",
      bg1: "#E7ECF3",
      ink: "#22344A",
      copper: "#B0602A",
      fiber: "#359CD3",
      red: "#D3121D",
      device: "#FFFFFF",
      led: "#2E9B76",
    },
    dark: {
      bg0: "#0A121C",
      bg1: "#131F2E",
      ink: "#A6B8C9",
      copper: "#D98A4B",
      fiber: "#5FC4F0",
      red: "#FF5A5F",
      device: "#162324",
      led: "#76CCAC",
    },
  },
};

/** The typed palette for one company and color mode — what a scene reads
 * instead of casting a loosely-typed shared palette. */
export function paletteFor<C extends TurksatCompany>(
  company: C,
  dark: boolean
): (typeof PAL)[C][TurksatMode] {
  return PAL[company][dark ? "dark" : "light"];
}
