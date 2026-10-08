import DOMPurify from "dompurify";

/**
 * Last line of defense before Mermaid's SVG reaches `innerHTML`.
 *
 * Mermaid already sanitizes labels with its own DOMPurify pass, but the
 * result is post-processed (id rescoping) and injected as raw markup, so it
 * is sanitized once more here with a fixed, strict profile: SVG and SVG
 * filters only, and never `<foreignObject>` (HTML inside SVG). Scripts, event
 * handler attributes and `javascript:` URLs are removed by DOMPurify itself.
 *
 * Without a DOM (SSR) there is nothing to sanitize with, so no markup is
 * returned; diagrams only render in the browser anyway.
 */
export function sanitizeMermaidSvg(svg: string): string {
  if (!DOMPurify.isSupported) return "";
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ["foreignObject"],
  });
}
