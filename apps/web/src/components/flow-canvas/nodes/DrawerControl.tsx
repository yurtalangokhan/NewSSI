import type { HTMLAttributes, KeyboardEvent } from "react";

interface DrawerControlProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "onClick" | "onKeyDown"> {
  onActivate: () => void;
  /** Set for a control that stays on, such as the current tab. */
  pressed?: boolean;
}

/**
 * A control inside the node drawer: click, Enter, or Space activates it. The
 * drawer sits on the canvas, so the event must not reach the node or pane.
 */
export function DrawerControl({
  onActivate,
  pressed,
  children,
  ...rest
}: DrawerControlProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    onActivate();
  };

  return (
    <div
      {...rest}
      role="button"
      tabIndex={0}
      aria-pressed={pressed}
      onClick={(event) => {
        event.stopPropagation();
        onActivate();
      }}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>
  );
}
