import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";

interface EntityColorDotProps {
  label: string;
}

/** A small dot in an entity type's palette colour, for legends and lists. */
export default function EntityColorDot({ label }: EntityColorDotProps) {
  return (
    <span
      className="h-2 w-2 shrink-0 rounded-full"
      style={{ backgroundColor: entityColorVar(entityColor(label), "05") }}
      aria-hidden
    />
  );
}
