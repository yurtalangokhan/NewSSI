/**
 * Type surface for the CommonJS helper `next.config.js` requires.
 *
 * Declared rather than left to inference: `types:check` runs `tsgo`, which
 * rejects a named import from a `module.exports = {...}` file (TS2497) where
 * `tsc` accepts it. Stating the shape here satisfies both compilers without
 * changing the helper, which has to stay plain CommonJS for next.config.js.
 */
export declare function requireEnv(
  name: string,
  rawValue: string | undefined
): string;
