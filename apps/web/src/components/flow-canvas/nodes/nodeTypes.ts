/**
 * xyflow renderer keys — the `type` field on a canvas node that selects which
 * React component draws it. Distinct from `data.type`, which is this app's
 * component type (e.g. "Chatbot", "ChatInput").
 *
 * Leaf module (no imports) so `compile.ts`, `useCanvasWiring`, `flowStore` and
 * `importFlow` can share these without an import cycle through the node
 * components.
 */
export const RendererNodeType = {
  Template: "templateNode",
  Note: "noteNode",
} as const;
export type RendererNodeType =
  (typeof RendererNodeType)[keyof typeof RendererNodeType];

/** `data.type` value that marks a node as a canvas sticky note. */
export const NOTE_COMPONENT_TYPE = "note";

/** Renderer key for a node given its component (`data.type`) value. */
export function rendererTypeForComponent(
  componentType: string
): RendererNodeType {
  return componentType === NOTE_COMPONENT_TYPE
    ? RendererNodeType.Note
    : RendererNodeType.Template;
}
