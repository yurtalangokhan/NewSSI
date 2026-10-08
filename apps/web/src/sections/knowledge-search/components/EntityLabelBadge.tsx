import Text from "@/refresh-components/texts/Text";
import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";

interface EntityLabelBadgeProps {
  label: string;
}

/** An entity type in its palette colour. */
export default function EntityLabelBadge({ label }: EntityLabelBadgeProps) {
  const color = entityColor(label);
  return (
    <span
      className="inline-flex items-center rounded-08 px-2 py-0.5"
      style={{
        backgroundColor: entityColorVar(color, "01"),
        color: entityColorVar(color, "05"),
      }}
    >
      <Text as="span" secondaryAction className="!text-inherit">
        {label}
      </Text>
    </span>
  );
}
