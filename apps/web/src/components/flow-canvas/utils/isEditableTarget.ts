/**
 * Concept ported from Langflow (MIT) — src/frontend/src/utils/is-wrapped-with-class.ts
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Adapted for Onyx: Langflow marks specific elements with a "noflow"/
 * "nodelete" class to opt out of canvas-level keyboard handling (so typing
 * in a field doesn't trigger flow delete/undo). Rather than requiring every
 * refresh-components input to carry that marker class, this checks the
 * event target's own editability directly — a plain `<input>`,
 * `<textarea>`, `[contenteditable]`, or `select` element. This is a
 * deliberate simplification: it needs no cross-cutting convention adopted
 * by every future field renderer (Task 26).
 *
 * Brief: .tmp/flow-canvas-task-24-brief.md
 */

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (EDITABLE_TAGS.has(target.tagName)) return true;
  if (target.isContentEditable) return true;
  return false;
}
