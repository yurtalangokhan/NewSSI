import Text from "@/refresh-components/texts/Text";

interface LabeledSectionProps {
  title: string;
  /** Heading level within the page outline. */
  as?: "h2" | "h3";
  /** Content placed on the heading row, after the title. */
  action?: React.ReactNode;
  children: React.ReactNode;
}

/** A block introduced by a small uppercase heading. */
export default function LabeledSection({
  title,
  as = "h3",
  action,
  children,
}: LabeledSectionProps) {
  return (
    <section className="flex w-full flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <Text
          as={as}
          secondaryAction
          text03
          className="uppercase tracking-wide"
        >
          {title}
        </Text>
        {action}
      </div>
      {children}
    </section>
  );
}
