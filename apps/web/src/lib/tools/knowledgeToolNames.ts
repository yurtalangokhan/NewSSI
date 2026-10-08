/** Tools (and flow retrieval nodes) whose results render as evidence cards. */
export const KNOWLEDGE_TOOL_NAMES: ReadonlySet<string> = new Set([
  "database_search",
  "graph_search",
  "document_search",
  "graph_entity_search",
  "graph_neighborhood",
]);
