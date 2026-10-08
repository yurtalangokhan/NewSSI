import { Interactive } from "@opal/core";
import { cn } from "@/lib/utils";

interface SearchHitCardFrameProps {
  selected: boolean;
  onOpen: () => void;
  children: React.ReactNode;
}

/** The clickable surface shared by document and entity result cards. */
export default function SearchHitCardFrame({
  selected,
  onOpen,
  children,
}: SearchHitCardFrameProps) {
  return (
    <Interactive.Base
      variant="select"
      prominence="light"
      selected={selected}
      group="group/HitCard"
      onClick={onOpen}
    >
      <Interactive.Container
        type="button"
        heightVariant="fit"
        widthVariant="full"
        roundingVariant="default"
        aria-haspopup="dialog"
      >
        <span
          className={cn(
            "flex w-full min-w-0 flex-col gap-2 rounded-12 border px-4 py-3.5 text-left transition-colors",
            selected
              ? "border-action-link-05 bg-action-link-01"
              : "border-border-01 bg-background-neutral-01 group-hover/HitCard:bg-background-tint-01"
          )}
        >
          {children}
        </span>
      </Interactive.Container>
    </Interactive.Base>
  );
}
