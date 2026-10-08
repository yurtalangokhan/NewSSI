/** Browser-only download helpers. Importing this module is DOM-free. */
import type { MermaidDiagramKind } from "@/components/mermaid/mermaidSource";
import {
  pngScale,
  readSvgSize,
  withPixelSize,
} from "@/components/mermaid/mermaidSvg";

const SVG_MIME = "image/svg+xml;charset=utf-8";

export function mermaidFileName(
  kind: MermaidDiagramKind | null,
  extension: "svg" | "png"
): string {
  return `${kind ? `diagram-${kind}` : "diagram"}.${extension}`;
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke after ~10 seconds to allow browser time to copy the blob to disk
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function downloadSvg(svg: string, fileName: string): void {
  downloadBlob(new Blob([svg], { type: SVG_MIME }), fileName);
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("SVG could not be decoded"));
    image.src = url;
  });
}

/**
 * Rasterizes the SVG at up to 2x on a filled background. Rejects if the SVG
 * cannot be decoded or the canvas is tainted; callers show a toast.
 *
 * Note: PNG export uses only system fonts (no web fonts). Mermaid diagrams
 * rendering through <img> do not load external stylesheets.
 */
export async function svgToPngBlob(
  svg: string,
  background: string
): Promise<Blob> {
  const size = readSvgSize(svg);
  if (!size) throw new Error("SVG has no viewBox");
  const scale = pngScale(size);
  const url = URL.createObjectURL(
    new Blob([withPixelSize(svg, size)], { type: SVG_MIME })
  );
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    // Floor (not ceil) so the rasterized area never exceeds pngScale's cap
    // by a stray row or column.
    canvas.width = Math.floor(size.width * scale);
    canvas.height = Math.floor(size.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas 2D context unavailable");
    context.fillStyle = background;
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) =>
          blob ? resolve(blob) : reject(new Error("PNG encoding failed")),
        "image/png"
      );
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}
