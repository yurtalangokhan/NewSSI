/**
 * Client-side mirror of apps/agent-service/src/domain/flows/handle_types.py.
 *
 * This is not a Langflow port — Langflow has no equivalent concept (its
 * component fields carry a fixed, hardcoded set of allowed input types
 * rather than a shared 9-value PortType lattice). This module exists so
 * illegal connections are rejected in `onConnect`, client-side, with no
 * request issued (design spec §10) — the server (P1 Task 3) re-validates
 * regardless and is the actual authority.
 *
 * The order below is load-bearing and mirrors the backend exactly:
 * identity -> Trigger isolation -> Data catch-all -> Data-as-source
 * rejection -> explicit coercions -> illegal. Trigger isolation outranking
 * the Data catch-all was a real bug on the backend (design spec amendment
 * F) — a Trigger is a pure signal with no payload, so it must not satisfy
 * a Data port just because Data otherwise accepts anything.
 *
 * See handleTypes.test.ts's 22.6 for how this is kept from silently
 * drifting out of sync with the backend.
 *
 * Brief: .tmp/flow-canvas-task-22-brief.md
 */

import type { PortType } from "../types/flow";

const EXPLICIT_COMPATIBLE: ReadonlySet<string> = new Set([
  serializePair("Message", "Text"),
]);

function serializePair(source: PortType, target: PortType): string {
  return `${source}->${target}`;
}

export function isCompatible(source: PortType, target: PortType): boolean {
  if (source === target) return true;
  if (source === "Trigger" || target === "Trigger") return false;
  if (target === "Data") return true;
  if (source === "Data") return false;
  return EXPLICIT_COMPATIBLE.has(serializePair(source, target));
}

/** A handle carries `types: PortType[]` (P1's Handle model) — compatible
 * if any pair across the two lists is compatible. */
export function handlesCompatible(
  sourceTypes: PortType[],
  targetTypes: PortType[]
): boolean {
  return sourceTypes.some((s) => targetTypes.some((t) => isCompatible(s, t)));
}
