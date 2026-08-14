const CATEGORY_TAG_REGEX = /\[category:([^\]]+)\]/;
const CATEGORY_LABEL_TAG_REGEX = /\[category_label:([^\]]+)\]/;
const TITLE_TAG_REGEX = /\[title:([^\]]+)\]/;

export interface ToolWithCategory {
  name: string;
  title?: string;
  description: string;
  input_schema: Record<string, any>;
  category?: string;
  categoryLabel?: string;
}

export function parseToolCategory(tool: ToolWithCategory): ToolWithCategory {
  if (!tool.description) return tool;

  const categoryMatch = tool.description.match(CATEGORY_TAG_REGEX);
  const labelMatch = tool.description.match(CATEGORY_LABEL_TAG_REGEX);
  const titleMatch = tool.description.match(TITLE_TAG_REGEX);

  if (categoryMatch || labelMatch || titleMatch) {
    return {
      ...tool,
      title: titleMatch ? titleMatch[1] : tool.title,
      category: categoryMatch ? categoryMatch[1] : undefined,
      categoryLabel: labelMatch ? labelMatch[1] : undefined,
      description: tool.description
        .replace(CATEGORY_TAG_REGEX, "")
        .replace(CATEGORY_LABEL_TAG_REGEX, "")
        .replace(TITLE_TAG_REGEX, "")
        .trim(),
    };
  }
  return tool;
}

export function groupToolsByCategory(
  tools: ToolWithCategory[]
): Record<string, ToolWithCategory[]> {
  const groups: Record<string, ToolWithCategory[]> = {};
  for (const tool of tools) {
    const cat = tool.category || "other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(tool);
  }
  return groups;
}

export function buildCategoryLabelMap(
  tools: ToolWithCategory[]
): Record<string, string> {
  const labelMap: Record<string, string> = {};
  for (const tool of tools) {
    const cat = tool.category || "other";
    if (!labelMap[cat] && tool.categoryLabel) {
      labelMap[cat] = tool.categoryLabel;
    }
  }
  return labelMap;
}
