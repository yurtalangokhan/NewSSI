"use client";

import {
  CHAT_BACKGROUND_OPTIONS,
  isCanvasBackground,
  isNoBackground,
  type ChatBackgroundOption,
} from "@/lib/constants/chatBackgrounds";
import { preloadChatBackgroundImage } from "@/lib/chatBackgroundClient";
import useResolvedColorMode from "@/hooks/useResolvedColorMode";
import { cn } from "@/lib/utils";
import { SvgCheck } from "@opal/icons";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { ChatBackgroundPreview } from "@/refresh-components/backgrounds/ChatBackgroundPreview";

interface ChatBackgroundPickerProps {
  selectedId: string;
  /** Text shown on the "none" tile. */
  noneLabel: string;
  onSelect: (option: ChatBackgroundOption) => void;
}

/** The row of background tiles in general settings. Each tile is named by the
 * app tooltip on hover/focus rather than the browser's native `title`. */
export function ChatBackgroundPicker({
  selectedId,
  noneLabel,
  onSelect,
}: ChatBackgroundPickerProps) {
  const canvasMode = useResolvedColorMode();

  return (
    <div className="flex flex-wrap gap-2">
      {CHAT_BACKGROUND_OPTIONS.map((option) => {
        const isSelected = selectedId === option.id;
        const warmCache = () => {
          if (!isCanvasBackground(option) && !isNoBackground(option)) {
            preloadChatBackgroundImage(option.src);
          }
        };

        return (
          <SimpleTooltip key={option.id} tooltip={option.label} side="bottom">
            <button
              onMouseEnter={warmCache}
              onFocus={warmCache}
              onClick={() => onSelect(option)}
              className="relative overflow-hidden rounded-lg transition-all w-[90px] h-[68px] cursor-pointer border-none p-0 bg-transparent group"
              aria-label={`${option.label} background${
                isSelected ? " (selected)" : ""
              }`}
            >
              <ChatBackgroundPreview
                option={option}
                canvasMode={canvasMode}
                noneContent={
                  <span className="text-xs text-text-02">{noneLabel}</span>
                }
              />
              <div
                className={cn(
                  "absolute inset-0 transition-all rounded-lg",
                  isSelected
                    ? "ring-2 ring-inset ring-theme-primary-05"
                    : "ring-1 ring-inset ring-border-02 group-hover:ring-border-03"
                )}
              />
              {isSelected && (
                <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-theme-primary-05 flex items-center justify-center">
                  <SvgCheck className="w-2.5 h-2.5 stroke-text-inverted-05" />
                </div>
              )}
            </button>
          </SimpleTooltip>
        );
      })}
    </div>
  );
}
