/**
 * Fail fast on a required env var instead of taking a silent fallback.
 *
 * Plain CommonJS on purpose: `next.config.js` runs as plain Node before the
 * app is bundled, so it cannot `import` the typed `src/lib/env` schema (zod +
 * `@t3-oss/env-nextjs`, TypeScript). `noStrayEnvReads.test.ts` only scans
 * `.tsx?` files under `src/`, which is this repo's own acknowledgement that
 * next.config.js is the one place outside that module structurally allowed to
 * read `process.env` directly -- it just had no shared helper to fail fast
 * with, so `AGENT_SERVICE_URL` silently fell back to
 * `"http://localhost:8080"` when unset instead of refusing to start the way
 * every other required URL does in `schema.ts`.
 *
 * Blank or whitespace-only counts as missing, matching `emptyStringAsUndefined`
 * in `src/lib/env/index.ts` -- a `configs/.env` line left as `KEY=` must not
 * read as "configured".
 *
 * @param {string} name - The env var's name, named in the thrown error.
 * @param {string | undefined} rawValue - `process.env[name]` at the call site.
 * @returns {string} The trimmed value.
 */
function requireEnv(name, rawValue) {
  const value = typeof rawValue === "string" ? rawValue.trim() : "";
  if (!value) {
    throw new Error(
      `${name} is required but was not set. Configure it in configs/.env.`
    );
  }
  return value;
}

module.exports = { requireEnv };
