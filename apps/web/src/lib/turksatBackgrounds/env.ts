import { VIRTUAL_H } from "./constants";
import type { Env, TurksatCompany } from "./types";

interface EnvSpec {
  company: TurksatCompany;
  dark: boolean;
  /** Virtual frame size (see `Painter`'s `frameFor`). */
  width: number;
  height: number;
  /** Where the authored 900-high scene sits in a taller frame, 0 (top edge)
   * to 1 (bottom edge). */
  anchorY: number;
  /** The message column's width in scene units. */
  columnWidth: number;
}

/** The message column may take at most this share of the frame, so the
 * compositions authored beside it still fit. */
const MAX_COLUMN_SHARE = 0.62;

/** Builds the layout environment a scene draws into: a `width` x `height`
 * virtual frame with the authored 900-high scene placed in it by `anchorY`,
 * and the centered message column (`colL`..`colR`) that animated elements dim
 * under (see `calmAt`). */
export function makeEnv({
  company,
  dark,
  width,
  height,
  anchorY,
  columnWidth,
}: EnvSpec): Env {
  const cx = width / 2;
  const colW = Math.min(columnWidth, width * MAX_COLUMN_SHARE);
  // `+ 0` folds a `-0` (from an anchor of 0) into 0.
  const top = (VIRTUAL_H - height) * anchorY + 0;
  return {
    company,
    dark,
    w: width,
    h: height,
    top,
    bottom: top + height,
    cx,
    colW,
    colL: cx - colW / 2,
    colR: cx + colW / 2,
  };
}
