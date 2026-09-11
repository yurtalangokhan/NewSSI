/**
 * Per-category icons for the component sidebar.
 *
 * Langflow gives every sidebar category its own glyph
 * (`categoryDisclouse.tsx:113-116` renders one next to the chevron), which
 * is a large part of why its palette reads as a set of families rather
 * than a flat list. The backend's categories are its own
 * (`domain/flows/templates/core.py`: core, models, agents, logic — plus
 * tools/knowledge once P5 lands), so the mapping is ours; the pattern is
 * upstream's.
 *
 * Unknown categories fall back to `SvgBlocks`, the same fallback
 * `resolveComponentIcon` uses, so a P5 category that lands before this map
 * is updated degrades to a generic glyph instead of a gap.
 */

import * as OpalIcons from "@opal/icons";
import type { ComponentType, SVGProps } from "react";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

const FALLBACK: IconComponent = OpalIcons.SvgBlocks as IconComponent;

const CATEGORY_ICONS: Record<string, IconComponent> = {
  core: OpalIcons.SvgBubbleText as IconComponent,
  models: OpalIcons.SvgCpu as IconComponent,
  agents: OpalIcons.SvgSparkle as IconComponent,
  logic: OpalIcons.SvgBranch as IconComponent,
  // P5 categories — registered ahead of the templates so the sidebar is
  // correct the day they land (Tasks 29-33).
  tools: OpalIcons.SvgWorkflow as IconComponent,
  knowledge: OpalIcons.SvgBookOpen as IconComponent,
};

export function resolveCategoryIcon(category: string): IconComponent {
  return CATEGORY_ICONS[category.toLowerCase()] ?? FALLBACK;
}
