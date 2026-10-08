import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";

interface PassageCardProps {
  /** Position or role of the passage, shown above it. */
  label?: string;
  highlighted?: boolean;
  testId?: string;
  children: React.ReactNode;
}

/** One document passage; the matched passage is highlighted. */
export default function PassageCard({
  label,
  highlighted = false,
  testId,
  children,
}: PassageCardProps) {
  return (
    <div
      data-testid={testId}
      className={cn(
        "flex flex-col gap-1.5 rounded-12 border px-3.5 py-3",
        highlighted
          ? "border-theme-amber-05 bg-theme-amber-01"
          : "border-border-01 bg-background-tint-01"
      )}
    >
      {label && (
        <Text as="span" secondaryMono text03>
          {label}
        </Text>
      )}
      <Text as="p" secondaryBody text04 className="whitespace-pre-wrap">
        {children}
      </Text>
    </div>
  );
}
