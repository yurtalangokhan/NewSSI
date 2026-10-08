/** The authored scene: 1440x900 (16:10). `Painter` fits it to any window by
 * growing the *frame* around it rather than cropping it — wider than 16:10
 * adds width, narrower adds height (the scene stays centered and its
 * backgrounds extend) — down to `MIN_FRAME_ASPECT` and up to
 * `MAX_FRAME_ASPECT`. Past those ratios the frame is cropped at the scene's
 * focal point instead. */
export const VIRTUAL_W = 1440;
export const VIRTUAL_H = 900;

/** Widest window (width/height) the frame widens for. */
export const MAX_FRAME_ASPECT = 3.6;

/** Narrowest window (width/height) the frame grows taller for. Narrower
 * (a phone) crops the sides rather than shrinking the scene to an
 * unreadable size. */
export const MIN_FRAME_ASPECT = 0.8;

export const TAU = Math.PI * 2;
export const DEG = Math.PI / 180;

export const MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';
