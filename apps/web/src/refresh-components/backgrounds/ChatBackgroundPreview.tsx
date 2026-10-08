import type { ReactNode } from "react";
import {
  isCanvasBackground,
  isNoBackground,
  type ChatBackgroundOption,
} from "@/lib/constants/chatBackgrounds";
import type { TurksatMode } from "@/lib/turksatBackgrounds/types";
import { TurksatBackgroundCanvas } from "@/refresh-components/backgrounds/TurksatBackgroundCanvas";

const HOVER_ZOOM_CLASS =
  "absolute inset-0 transition-transform duration-300 group-hover:scale-105";

interface ChatBackgroundPreviewProps {
  option: ChatBackgroundOption;
  /** The color mode a canvas scene is previewed in. */
  canvasMode: TurksatMode;
  /** What the "none" option shows in place of a picture. */
  noneContent: ReactNode;
}

/**
 * The picture inside a background picker tile: a static frame of a canvas
 * scene, a photo thumbnail, or the caller's "none" placeholder. The tile's
 * button, ring, and selection check stay with the caller.
 */
export function ChatBackgroundPreview({
  option,
  canvasMode,
  noneContent,
}: ChatBackgroundPreviewProps) {
  if (isNoBackground(option)) {
    return (
      <div className="absolute inset-0 bg-background flex items-center justify-center">
        {noneContent}
      </div>
    );
  }
  if (isCanvasBackground(option)) {
    return (
      <TurksatBackgroundCanvas
        company={option.canvas.company}
        mode={canvasMode}
        animate={false}
        className={HOVER_ZOOM_CLASS}
      />
    );
  }
  return (
    <div
      className={`${HOVER_ZOOM_CLASS} bg-cover bg-center`}
      style={{ backgroundImage: `url(${option.thumbnail})` }}
    />
  );
}
