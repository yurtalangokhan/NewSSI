import { GroupedPacket } from "./hooks/packetProcessor";
import { PacketType } from "@/app/app/services/streamingModels";
import { getReasoningTextContent } from "@/app/app/services/packetUtils";

/**
 * Transformed step data ready for rendering
 */
export interface TransformedStep {
  /** Unique key for React rendering */
  key: string;
  /** Turn index from packet placement */
  turnIndex: number;
  /** Tab index for parallel tools */
  tabIndex: number;
  /** Raw packets for content rendering */
  packets: GroupedPacket["packets"];
}

/**
 * Group steps by turn_index for detecting parallel tools
 */
export interface TurnGroup {
  turnIndex: number;
  steps: TransformedStep[];
  /** True if multiple steps have the same turn_index (parallel execution) */
  isParallel: boolean;
}

/**
 * Transform a single GroupedPacket into step data
 */
export function transformPacketGroup(group: GroupedPacket): TransformedStep {
  return {
    key: `${group.turn_index}-${group.tab_index}`,
    turnIndex: group.turn_index,
    tabIndex: group.tab_index,
    packets: group.packets,
  };
}

/**
 * Transform all packet groups into step data
 */
export function transformPacketGroups(
  groups: GroupedPacket[]
): TransformedStep[] {
  const steps = groups.map(transformPacketGroup);
  const result: TransformedStep[] = [];
  const seenReasoningTexts = new Set<string>();

  for (const step of steps) {
    const isReasoning = step.packets.some(
      (p) =>
        p.obj.type === PacketType.REASONING_START ||
        p.obj.type === PacketType.REASONING_DELTA
    );

    if (isReasoning) {
      const text = getReasoningTextContent(step.packets).trim();
      if (text) {
        const isDuplicate = Array.from(seenReasoningTexts).some(
          (seen) =>
            seen === text ||
            (text.length > 50 &&
              seen.length > 50 &&
              (seen.startsWith(text) || text.startsWith(seen)))
        );
        if (isDuplicate) {
          continue;
        }
        seenReasoningTexts.add(text);
      }
    }

    result.push(step);
  }

  return result;
}

/**
 * Group transformed steps by turn_index to detect parallel tools
 *
 * @example
 * // Input: TransformedStep[]
 * // ┌──────────────────────────────────────────┐
 * // │ [0] key="0-0" turnIndex=0 tabIndex=0     │
 * // │ [1] key="0-1" turnIndex=0 tabIndex=1     │
 * // │ [2] key="1-0" turnIndex=1 tabIndex=0     │
 * // └──────────────────────────────────────────┘
 * //
 * // Step 1: Build Map<turnIndex, TransformedStep[]>
 * // ┌─────────────────────────────────────────────┐
 * // │ turnMap = {                                 │
 * // │   0 → [step(0-0), step(0-1)]               │
 * // │   1 → [step(1-0)]                          │
 * // │ }                                          │
 * // └─────────────────────────────────────────────┘
 * //
 * // Step 2: Sort turn indices & steps by tabIndex
 * //
 * // Step 3: Build TurnGroup[] with isParallel flag
 * // ┌─────────────────────────────────────────────┐
 * // │ Output: TurnGroup[]                         │
 * // ├─────────────────────────────────────────────┤
 * // │ [0] turnIndex=0                             │
 * // │     steps=[0-0, 0-1]                        │
 * // │     isParallel=true  ← 2 steps = parallel   │
 * // │                                             │
 * // │ [1] turnIndex=1                             │
 * // │     steps=[1-0]                             │
 * // │     isParallel=false ← 1 step = sequential  │
 * // └─────────────────────────────────────────────┘
 */
export function groupStepsByTurn(steps: TransformedStep[]): TurnGroup[] {
  const turnMap = new Map<number, TransformedStep[]>();

  for (const step of steps) {
    const existing = turnMap.get(step.turnIndex);
    if (existing) {
      existing.push(step);
    } else {
      turnMap.set(step.turnIndex, [step]);
    }
  }

  const result: TurnGroup[] = [];
  const sortedTurnIndices = Array.from(turnMap.keys()).sort((a, b) => a - b);

  for (const turnIndex of sortedTurnIndices) {
    const stepsForTurn = turnMap.get(turnIndex)!;
    stepsForTurn.sort((a, b) => a.tabIndex - b.tabIndex);

    result.push({
      turnIndex,
      steps: stepsForTurn,
      isParallel: stepsForTurn.length > 1,
    });
  }

  return result;
}
