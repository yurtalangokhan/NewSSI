export type InputSchema = {
  type: "object";
  properties?: Record<string, any>;
  required?: string[];
};

export interface Tool {
  /**
   * The name of the tool
   */
  name: string;
  /**
   * The tool's description (may contain [category:xxx] tag)
   */
  description?: string;
  /**
   * The tool's input schema
   */
  inputSchema: InputSchema;
  /**
   * The tool's category (parsed from description tag)
   */
  category?: string;
  /**
   * The tool's category display label (parsed from description tag)
   */
  categoryLabel?: string;
}

/**
 * Category tag pattern: [category:name]
 * Category label tag pattern: [category_label:label]
 */
const CATEGORY_TAG_REGEX = /\[category:([^\]]+)\]/;
const CATEGORY_LABEL_TAG_REGEX = /\[category_label:([^\]]+)\]/;

/**
 * Parse the [category:xxx] and [category_label:xxx] tags from a tool's description,
 * extract the category name and label, and return clean description.
 */
export function parseToolCategory(tool: Tool): Tool {
  if (!tool.description) return tool;

  const categoryMatch = tool.description.match(CATEGORY_TAG_REGEX);
  const labelMatch = tool.description.match(CATEGORY_LABEL_TAG_REGEX);

  if (categoryMatch || labelMatch) {
    return {
      ...tool,
      category: categoryMatch ? categoryMatch[1] : undefined,
      categoryLabel: labelMatch ? labelMatch[1] : undefined,
      description: tool.description
        .replace(CATEGORY_TAG_REGEX, "")
        .replace(CATEGORY_LABEL_TAG_REGEX, "")
        .trim(),
    };
  }
  return tool;
}

/**
 * Group tools by their category.
 * Tools without category go under "other".
 */
export function groupToolsByCategory(
  tools: Tool[],
): Record<string, Tool[]> {
  const groups: Record<string, Tool[]> = {};
  for (const tool of tools) {
    const cat = tool.category || "other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(tool);
  }
  return groups;
}

/**
 * Build a mapping from category name to its display label.
 * Uses the categoryLabel from the first tool in each category.
 * Falls back to startCase(category) if no label is available.
 */
export function buildCategoryLabelMap(
  tools: Tool[],
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
