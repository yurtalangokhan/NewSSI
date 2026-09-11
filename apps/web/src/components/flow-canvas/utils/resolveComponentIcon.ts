/**
 * Resolves a ComponentTemplate's `icon` field (a kebab-case name from P1's
 * backend `ICON_ALLOWLIST`, e.g. "sparkle") to the matching `@opal/icons`
 * component (`SvgSparkle`), per STANDARDS §8 — only icons from the curated
 * set, never lucide/react-icons.
 *
 * Nothing structurally keeps the backend's allowlist and this frontend's
 * icon barrel in sync (P1 Task 2's report flagged the same gap) — an
 * unknown name degrades to a generic fallback icon rather than blanking
 * the palette (25.8).
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import * as OpalIcons from "@opal/icons";
import type { ComponentType, SVGProps } from "react";

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

const FALLBACK_ICON: IconComponent = OpalIcons.SvgBlocks as IconComponent;

function toPascalCase(kebabCase: string): string {
  return kebabCase
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

export function resolveComponentIcon(
  iconName: string | null | undefined
): IconComponent {
  if (!iconName) return FALLBACK_ICON;
  const icons = OpalIcons as unknown as Record<
    string,
    IconComponent | undefined
  >;
  if (icons[iconName]) return icons[iconName]!;
  const exportName = "Svg" + toPascalCase(iconName);
  return icons[exportName] ?? FALLBACK_ICON;
}
