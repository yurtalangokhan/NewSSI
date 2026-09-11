"use client";

import { useTranslation } from "react-i18next";
import Popover from "@/refresh-components/Popover";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { cn } from "@/lib/utils";

/**
 * The sticky note's two bespoke surfaces, kept out of `nodes/` so
 * `NoteNode` never writes a raw `<button>`/`<textarea>` itself (guard:
 * __tests__/rawHtmlGuard.test.ts). Neither maps onto a `refresh-components`
 * primitive: the picker's controls are colour swatches, not icons, and the
 * note body must be a fully transparent, borderless textarea that fills the
 * (resizable) note and inherits the note's text colour — none of which
 * `InputTextArea` can express. Same escape hatch `components/JsonCodeEditor`
 * already uses for its editor surface.
 */

export interface NoteColorOption {
  dot: string;
  label: string;
}

interface NoteColorPickerProps {
  colors: Record<string, NoteColorOption>;
  activeColorKey: string;
  activeDotClassName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (colorKey: string) => void;
}

export function NoteColorPicker({
  colors,
  activeColorKey,
  activeDotClassName,
  open,
  onOpenChange,
  onSelect,
}: NoteColorPickerProps) {
  const { t } = useTranslation();
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger asChild>
        <div>
          <SimpleTooltip
            tooltip={t("flowCanvas.stickyNote.color", "Color")}
            side="top"
          >
            <button
              type="button"
              aria-label={t(
                "flowCanvas.stickyNote.changeColor",
                "Change color"
              )}
              className="flex h-7 w-7 items-center justify-center rounded-06 transition-colors hover:bg-background-tint-02"
            >
              <span
                className={cn(
                  "h-4 w-4 rounded-full border border-border shadow-xs",
                  activeDotClassName
                )}
              />
            </button>
          </SimpleTooltip>
        </div>
      </Popover.Trigger>
      <Popover.Content align="start" width="fit">
        <div className="flex items-center gap-1.5 p-1.5">
          {Object.entries(colors).map(([key, item]) => (
            <SimpleTooltip
              key={key}
              tooltip={t(`flowCanvas.stickyNote.colors.${key}`, item.label)}
              side="top"
            >
              <button
                type="button"
                onClick={() => onSelect(key)}
                aria-label={t(
                  `flowCanvas.stickyNote.colors.${key}`,
                  item.label
                )}
                className={cn(
                  "h-5 w-5 rounded-full border border-border-02 transition-transform hover:scale-110",
                  item.dot,
                  key === activeColorKey &&
                    "ring-2 ring-primary ring-offset-1 scale-110"
                )}
              />
            </SimpleTooltip>
          ))}
        </div>
      </Popover.Content>
    </Popover>
  );
}

interface NoteTextAreaProps {
  value: string;
  onChange: (event: React.ChangeEvent<HTMLTextAreaElement>) => void;
  className?: string;
}

export function NoteTextArea({
  value,
  onChange,
  className,
}: NoteTextAreaProps) {
  const { t } = useTranslation();
  return (
    <textarea
      value={value}
      onChange={onChange}
      onPointerDown={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      placeholder={t("flowCanvas.stickyNote.placeholder", "Write a note...")}
      className={cn(
        "nowheel nodrag h-full w-full flex-1 resize-none bg-transparent font-sans text-sm leading-relaxed outline-none placeholder:text-current placeholder:opacity-50 cursor-text",
        className
      )}
    />
  );
}
