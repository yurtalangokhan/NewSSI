// Default chat background images, plus the TÜRKSAT animated backgrounds.
import type { TurksatCompany } from "@/lib/turksatBackgrounds/types";

export const CHAT_BACKGROUND_NONE = "none";
export const CHAT_BACKGROUND_COOKIE_NAME = "agentic_chat_background";

interface ChatBackgroundBase {
  id: string;
  label: string;
}

/** A fixed photo, painted as a CSS `background-image`. `CHAT_BACKGROUND_NONE`
 * is expressed as an image option whose `src` is the "none" sentinel. */
export interface ImageBackgroundOption extends ChatBackgroundBase {
  kind?: "image";
  src: string;
  thumbnail: string;
  /** Fixed darkness of the photo; it dictates the app color mode. */
  isDarkBackground?: boolean;
}

/** A live `TurksatBackgroundCanvas` scene. It has no image to fetch, and its
 * darkness follows the resolved color mode — read it from
 * `useAppBackground().appBackground`, which resolves it. */
export interface CanvasBackgroundOption extends ChatBackgroundBase {
  kind: "canvas";
  canvas: { company: TurksatCompany };
}

export type ChatBackgroundOption =
  | ImageBackgroundOption
  | CanvasBackgroundOption;

export function isCanvasBackground(
  option: ChatBackgroundOption
): option is CanvasBackgroundOption {
  return option.kind === "canvas";
}

/** True when nothing should be painted: the "none" option or an unknown id. */
export function isNoBackground(
  option: ChatBackgroundOption | undefined
): boolean {
  return (
    !option ||
    (!isCanvasBackground(option) && option.src === CHAT_BACKGROUND_NONE)
  );
}

/** The color mode a fixed photo dictates, or `null` when the user stays free
 * to choose it ("none" and canvas scenes, which follow the color mode). */
export function getLockedColorMode(
  option: ChatBackgroundOption
): "light" | "dark" | null {
  if (isCanvasBackground(option) || isNoBackground(option)) return null;
  return option.isDarkBackground ? "dark" : "light";
}

function turksatOption(
  id: string,
  label: string,
  company: TurksatCompany
): CanvasBackgroundOption {
  return { id, label, kind: "canvas", canvas: { company } };
}

// Curated collection of scenic backgrounds that work well as chat backgrounds
export const CHAT_BACKGROUND_OPTIONS: ChatBackgroundOption[] = [
  {
    id: "none",
    src: CHAT_BACKGROUND_NONE,
    thumbnail: CHAT_BACKGROUND_NONE,
    label: "None",
    isDarkBackground: false,
  },
  {
    id: "clouds",
    src: "/chat-backgrounds/clouds.jpg",
    thumbnail: "/chat-backgrounds/thumbnails/clouds.jpg",
    label: "Clouds",
    isDarkBackground: false,
  },
  {
    id: "hills",
    src: "/chat-backgrounds/hills.jpg",
    thumbnail: "/chat-backgrounds/thumbnails/hills.jpg",
    label: "Hills",
    isDarkBackground: false,
  },
  {
    id: "plant",
    src: "/chat-backgrounds/plant.jpg",
    thumbnail: "/chat-backgrounds/thumbnails/plant.jpg",
    label: "Plants",
    isDarkBackground: true,
  },
  {
    id: "mountains",
    src: "/chat-backgrounds/mountains.jpg",
    thumbnail: "/chat-backgrounds/thumbnails/mountains.jpg",
    label: "Mountains",
    isDarkBackground: true,
  },
  {
    id: "night",
    src: "/chat-backgrounds/night.jpg",
    thumbnail: "/chat-backgrounds/thumbnails/night.jpg",
    label: "Night",
    isDarkBackground: true,
  },
  turksatOption("turksat-bilisim", "Türksat Bilişim", "bilisim"),
  turksatOption("turksat-uydu", "Türksat Uydu", "uydu"),
  turksatOption("turksat-kablo", "Türksat Kablo", "kablo"),
];

export const getBackgroundById = (
  id: string | null
): ChatBackgroundOption | undefined => {
  if (!id || id === CHAT_BACKGROUND_NONE) {
    return CHAT_BACKGROUND_OPTIONS[0];
  }
  return CHAT_BACKGROUND_OPTIONS.find((bg) => bg.id === id);
};
