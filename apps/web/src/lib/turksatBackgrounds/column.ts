/** The CSS variable that sizes the app's message column (see `sizes.css`). */
const COLUMN_WIDTH_VAR = "var(--app-page-main-content-width)";

/** The variable's design value (52.5rem at a 16px root), used when the real
 * width cannot be measured. */
export const DEFAULT_COLUMN_CSS_PX = 840;

/**
 * The on-screen width, in CSS pixels, of the app's message column beside a
 * background canvas. Scenes dim what animates behind that column, so it is
 * measured from the same CSS the column uses (rem, the variable, and the
 * container's own width as a cap) instead of being guessed in scene units.
 */
export function measureColumnCssPx(canvas: HTMLElement): number {
  const host = canvas.parentElement ?? document.body;
  const probe = document.createElement("div");
  probe.setAttribute("aria-hidden", "true");
  probe.style.cssText = `position:absolute;visibility:hidden;pointer-events:none;height:0;width:${COLUMN_WIDTH_VAR};max-width:100%`;
  host.append(probe);
  const width = probe.offsetWidth;
  probe.remove();
  return width > 0 ? width : DEFAULT_COLUMN_CSS_PX;
}
