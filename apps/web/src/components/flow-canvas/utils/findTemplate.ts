import type {
  ComponentTemplate,
  GroupedComponentTemplates,
} from "../types/componentTemplate";

export function findTemplateByType(
  grouped: GroupedComponentTemplates,
  type: string
): ComponentTemplate | undefined {
  for (const templates of Object.values(grouped)) {
    const found = templates.find((t) => t.type === type);
    if (found) return found;
  }
  return undefined;
}
