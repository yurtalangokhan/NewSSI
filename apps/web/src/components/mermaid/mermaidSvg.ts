/**
 * Pure helpers for Mermaid SVG strings.
 *
 * Mermaid prefixes every internal id and CSS selector with the render id.
 * Two copies of one SVG on a page (a cached diagram shown twice, or the
 * fullscreen viewer) would otherwise share marker ids, and a marker defined
 * in a hidden or removed copy breaks arrows in the visible one. Every on-page
 * copy therefore gets its own scope id.
 */

let scopeCounter = 0;

/** `mmdv<n>z`: the trailing `z` stops `mmdv1z` from matching inside `mmdv12z`. */
export function createSvgScopeId(): string {
  scopeCounter += 1;
  return `mmdv${scopeCounter}z`;
}

const OPENING_TAG = /<[a-zA-Z][^>]*>/g;
const STYLE_BLOCK = /<style[^>]*>[\s\S]*?<\/style>/gi;

const REGEXP_SPECIAL = /[.*+?^${}()|[\]\\]/g;

/** Escapes a literal string for safe embedding in a `RegExp` source. */
function escapeForRegExp(value: string): string {
  return value.replace(REGEXP_SPECIAL, "\\$&");
}

/**
 * Rescopes every mermaid-owned id in `svg` from `fromId` to `toId`.
 *
 * Ids are user-authored (node names, class names, state names) and may
 * contain regex metacharacters, so every id is treated as a literal and
 * matched only inside the attributes and selectors mermaid actually uses:
 * `id="…"`, `href="#…"`/`xlink:href="#…"`, `url(#…)`, `aria-labelledby`/
 * `aria-describedby`, and `#id` CSS selectors inside `<style>`. Ids are also
 * collected only from real `id="…"` attributes (a tag boundary before the
 * name), so a label or attribute value that merely contains `id="x"` text is
 * neither collected nor rewritten. Text content that happens to read like an
 * id or `url(#id)` reference is left alone unless a real element owns it.
 */
export function rescopeSvgIds(
  svg: string,
  fromId: string,
  toId: string
): string {
  if (fromId === "" || fromId === toId) return svg;

  // Collect every id value declared on the SVG.
  const idMap = new Map<string, string>();
  const ownIds: string[] = [];
  for (const tag of svg.match(OPENING_TAG) ?? []) {
    const idRegex = /(?:^|[\s"'])id="([^"]*)"/g;
    let match;
    while ((match = idRegex.exec(tag)) !== null) {
      if (match[1]) ownIds.push(match[1]);
    }
  }
  for (const id of ownIds) {
    if (idMap.has(id)) continue;

    if (id.startsWith(fromId)) {
      // Prefixed id (includes the root id itself): replace the prefix.
      idMap.set(id, toId + id.slice(fromId.length));
    } else {
      // Unprefixed id (common in sequence diagrams): prepend new scope and dash.
      idMap.set(id, `${toId}-${id}`);
    }
  }
  if (idMap.size === 0) return svg;

  // Longest id first so an alternation match cannot stop short at a shorter
  // id that happens to be a prefix of a longer one at the same position.
  const ids = Array.from(idMap.keys()).sort((a, b) => b.length - a.length);
  const alternation = ids.map(escapeForRegExp).join("|");

  // The character before an attribute name must not be `-` or a word
  // character, or mermaid's own `data-id="…"` bookkeeping would be rewritten.
  // A capture group is used instead of a lookbehind so the boundary is kept.
  const BOUNDARY = `(^|[\\s"'<])`;
  const idAttributes = new RegExp(
    `${BOUNDARY}(id|aria-labelledby|aria-describedby)="(${alternation})"`,
    "g"
  );
  const hrefAttributes = new RegExp(
    `${BOUNDARY}(xlink:href|href)="#(${alternation})"`,
    "g"
  );
  const urlReference = new RegExp(`url\\(#(${alternation})\\)`, "g");
  const rewriteUrl = (segment: string) =>
    segment.replace(
      urlReference,
      (_whole, id: string) => `url(#${idMap.get(id)})`
    );

  // Attributes are rewritten only inside opening tags, never in text content,
  // so a label that reads like `id="x"` or `url(#x)` stays as written.
  let result = svg.replace(OPENING_TAG, (tag) =>
    rewriteUrl(
      tag
        .replace(
          idAttributes,
          (_whole, boundary: string, attr: string, id: string) =>
            `${boundary}${attr}="${idMap.get(id)}"`
        )
        .replace(
          hrefAttributes,
          (_whole, boundary: string, attr: string, id: string) =>
            `${boundary}${attr}="#${idMap.get(id)}"`
        )
    )
  );

  // `url(#X)` inside <style> blocks (fills, filters).
  result = result.replace(STYLE_BLOCK, rewriteUrl);

  // `#X` CSS selectors, but only inside <style> blocks — never in text
  // content. Exact-id match: the id must not continue into more
  // identifier characters (guards `#actor1` against `#actor10`).
  result = result.replace(STYLE_BLOCK, (styleBlock) =>
    styleBlock.replace(
      new RegExp(`#(${alternation})(?![A-Za-z0-9_-])`, "g"),
      (_whole, id: string) => `#${idMap.get(id)}`
    )
  );

  return result;
}

export interface SvgSize {
  width: number;
  height: number;
}

const ROOT_TAG = /<svg\b[^>]*>/i;
const VIEW_BOX =
  /\bviewBox="\s*-?[\d.]+[\s,]+-?[\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)\s*"/i;

export function readSvgSize(svg: string): SvgSize | null {
  const root = ROOT_TAG.exec(svg)?.[0];
  if (!root) return null;
  const viewBox = VIEW_BOX.exec(root);
  if (!viewBox) return null;
  const width = Number(viewBox[1]);
  const height = Number(viewBox[2]);
  return width > 0 && height > 0 ? { width, height } : null;
}

/** Browsers refuse canvases much beyond this per side. */
export const PNG_MAX_SIDE = 8192;

/** iOS canvas limit (16M px, applies to total area). */
const PNG_MAX_AREA = 16777216;

export function pngScale(
  size: SvgSize,
  desired = 2,
  maxSide = PNG_MAX_SIDE
): number {
  const sideScale = Math.min(maxSide / size.width, maxSide / size.height);
  const areaScale = Math.sqrt(PNG_MAX_AREA / (size.width * size.height));
  return Math.min(desired, sideScale, areaScale);
}

/** Mermaid emits width="100%"; <img> decoding needs pixel dimensions. */
export function withPixelSize(svg: string, size: SvgSize): string {
  return svg.replace(ROOT_TAG, (root) =>
    root
      .replace(/\s(width|height)="[^"]*"/gi, "")
      .replace(/^<svg/i, `<svg width="${size.width}" height="${size.height}"`)
  );
}

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
  "&apos;": "'",
};

function readSvgText(svg: string, tag: "title" | "desc"): string | null {
  const match = new RegExp(`<${tag}\\b[^>]*>([^<]*)</${tag}>`, "i").exec(svg);
  const text = match?.[1]
    ?.replace(/&(?:amp|lt|gt|quot|apos|#39);/g, (entity) => ENTITIES[entity]!)
    .trim();
  return text ? text : null;
}

/**
 * The author-provided accessible name (`accTitle` / `accDescr`), which
 * Mermaid writes as `<title>` and `<desc>`. Null when the diagram has none.
 */
export function readSvgAccessibleName(svg: string): string | null {
  const title = readSvgText(svg, "title");
  const description = readSvgText(svg, "desc");
  if (title && description) return `${title}. ${description}`;
  return title ?? description;
}
