import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";

interface EntityDotProps {
  label: string;
  matched?: boolean;
}

/** The entity marker of cards and previews: filled when matched, a ring otherwise. */
export default function EntityDot({ label, matched = true }: EntityDotProps) {
  const color = entityColor(label);
  return (
    <span
      className="flex h-[1.625rem] w-[1.625rem] shrink-0 items-center justify-center rounded-full"
      style={{ backgroundColor: entityColorVar(color, "01") }}
      aria-hidden
    >
      <span
        className="block h-2.5 w-2.5 rounded-full"
        style={
          matched
            ? { backgroundColor: entityColorVar(color, "05") }
            : { boxShadow: `inset 0 0 0 2px ${entityColorVar(color, "05")}` }
        }
      />
    </span>
  );
}
