/**
 * Entity label → Atlas theme colour. Common labels get a fixed colour so the
 * same kind of entity always looks the same; anything else hashes into the
 * palette, so colours stay stable across reloads without a server contract.
 */
export type EntityColor =
  | "cyan"
  | "purple"
  | "amber"
  | "green"
  | "blue"
  | "orange"
  | "red"
  | "lime";

const PALETTE: readonly EntityColor[] = [
  "cyan",
  "purple",
  "amber",
  "green",
  "blue",
  "orange",
  "red",
  "lime",
];

const KNOWN_LABELS: Readonly<Record<string, EntityColor>> = {
  process: "cyan",
  event: "cyan",
  person: "purple",
  role: "purple",
  organization: "amber",
  department: "amber",
  company: "amber",
  document: "blue",
  policy: "blue",
  rule: "green",
  concept: "green",
  location: "orange",
  product: "lime",
};

export function entityColor(label: string): EntityColor {
  const known = KNOWN_LABELS[label.toLowerCase()];
  if (known) return known;
  let hash = 0;
  for (let index = 0; index < label.length; index += 1) {
    hash = (hash * 31 + label.charCodeAt(index)) | 0;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length]!;
}

/** CSS custom property for the colour: `05` is the ink, `01` the soft fill. */
export function entityColorVar(color: EntityColor, shade: "01" | "05"): string {
  return `var(--theme-${color}-${shade})`;
}
