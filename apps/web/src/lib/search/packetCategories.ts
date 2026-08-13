/**
 * Registry that declares how each backend packet type behaves in the streaming
 * timeline pipeline.
 *
 * Adding a new step type only requires adding / editing an entry in
 * PACKET_CATEGORIES — streamingUtils and packetProcessor derive all their
 * logic from this file.
 */

export interface PacketCategory {
  /** Unique identifier for this category. */
  id: string;
  /** All packet types that belong to this category. */
  types: ReadonlySet<string>;
  /**
   * Optional suffix appended to the group key so that packets of this category
   * get their own virtual group even when they share a turn_index with packets
   * of another category.  Example: "ltm" produces keys like "3-0-ltm".
   */
  groupSuffix?: string;
  /**
   * When true, a transition between this category and any other category
   * (in either direction) should advance the turn_index.
   */
  splitsFromOthers: boolean;
}

/**
 * Single source of truth for all agent-service packet categorisation.
 *
 * Order does not matter — lookups use Set membership, not array position.
 */
export const PACKET_CATEGORIES: ReadonlyArray<PacketCategory> = [
  {
    id: "memory",
    types: new Set([
      "long_term_memory_recall",
      "long_term_memory_save",
    ]),
    groupSuffix: "ltm",
    splitsFromOthers: true,
  },
  {
    id: "reasoning",
    types: new Set([
      "reasoning_start",
      "reasoning_delta",
      "reasoning_done",
    ]),
    groupSuffix: "reasoning",
    splitsFromOthers: true,
  },
  {
    id: "tool",
    types: new Set([
      "custom_tool_start",
      "custom_tool_delta",
      "custom_step_start",
      "search_tool_start",
      "search_tool_queries_delta",
      "search_tool_documents_delta",
    ]),
    splitsFromOthers: false,
  },
  {
    id: "generated-file",
    types: new Set(["generated_file"]),
    groupSuffix: "genfile",
    splitsFromOthers: true,
  },
] as const;

// ---------------------------------------------------------------------------
// Derived helpers — consumers import these; they never maintain sets manually.
// ---------------------------------------------------------------------------

/** All packet types across every category (used to detect tool vs display). */
export const TOOL_PACKET_TYPES: ReadonlySet<string> = new Set(
  PACKET_CATEGORIES.flatMap((c) => Array.from(c.types))
);

/** Return the category that owns `type`, or undefined for unknown types. */
export function getCategoryFor(type: string): PacketCategory | undefined {
  return PACKET_CATEGORIES.find((c) => c.types.has(type));
}

/**
 * Return the group-key suffix for `type`, or undefined if the type uses the
 * default (turn_index + tab_index only) group key.
 */
export function getGroupSuffix(type: string): string | undefined {
  return getCategoryFor(type)?.groupSuffix;
}

/**
 * Return true if adjacent packets of type `prevType` and `nextType` should be
 * placed in different turn groups.
 *
 * Two packets split when they belong to different categories AND at least one
 * of those categories has splitsFromOthers = true.
 */
export function shouldSplitCategories(
  prevType: string,
  nextType: string
): boolean {
  const prev = getCategoryFor(prevType);
  const next = getCategoryFor(nextType);
  if (prev === next) return false;
  return (prev?.splitsFromOthers ?? false) || (next?.splitsFromOthers ?? false);
}
