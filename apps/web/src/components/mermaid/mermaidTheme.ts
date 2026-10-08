/**
 * Mermaid "base" theme driven by the app's CSS colour tokens
 * (src/app/css/colors.css). Mermaid's colour math only understands concrete
 * colours, so tokens are resolved at runtime and flattened to opaque hex
 * (text tokens are alpha colours such as #000000e5).
 */

export interface MermaidThemeConfig {
  /** Fingerprint of everything below; part of the render cache key. */
  key: string;
  darkMode: boolean;
  fontFamily: string;
  themeVariables: Record<string, string | boolean>;
}

export type TokenReader = (token: string) => string;

export interface Rgba {
  r: number;
  g: number;
  b: number;
  a: number;
}

export const DEFAULT_MERMAID_FONT_FAMILY =
  '"Hanken Grotesk", ui-sans-serif, system-ui, sans-serif';

/** Mermaid themeVariable → project CSS custom property. */
export const MERMAID_THEME_TOKENS = {
  background: "--background-tint-00",
  primaryColor: "--background-tint-02",
  primaryBorderColor: "--border-03",
  primaryTextColor: "--text-05",
  secondaryColor: "--background-tint-03",
  secondaryBorderColor: "--border-02",
  secondaryTextColor: "--text-05",
  tertiaryColor: "--background-tint-01",
  tertiaryBorderColor: "--border-02",
  tertiaryTextColor: "--text-04",
  lineColor: "--text-03",
  textColor: "--text-04",
  noteBkgColor: "--status-warning-01",
  noteTextColor: "--text-05",
  noteBorderColor: "--status-warning-05",
  errorBkgColor: "--status-error-01",
  errorTextColor: "--status-error-05",
} as const;

type ThemeVariableName = keyof typeof MERMAID_THEME_TOKENS;

function channel(part: string): number {
  return part.endsWith("%")
    ? Math.round(parseFloat(part) * 2.55)
    : parseFloat(part);
}

export function parseCssColor(value: string): Rgba | null {
  const text = value.trim().toLowerCase();
  const hex = /^#([0-9a-f]{3,8})$/.exec(text);
  if (hex) {
    const digits = hex[1]!;
    if (digits.length === 3 || digits.length === 4) {
      const [r, g, b, a = "f"] = digits.split("");
      return {
        r: parseInt(r! + r!, 16),
        g: parseInt(g! + g!, 16),
        b: parseInt(b! + b!, 16),
        a: parseInt(a + a, 16) / 255,
      };
    }
    if (digits.length === 6 || digits.length === 8) {
      return {
        r: parseInt(digits.slice(0, 2), 16),
        g: parseInt(digits.slice(2, 4), 16),
        b: parseInt(digits.slice(4, 6), 16),
        a: digits.length === 8 ? parseInt(digits.slice(6, 8), 16) / 255 : 1,
      };
    }
    return null;
  }
  const fn = /^rgba?\(([^)]+)\)$/.exec(text);
  if (!fn) return null;
  const parts = fn[1]!.split(/[\s,/]+/).filter((part) => part !== "");
  if (parts.length < 3) return null;
  const alphaPart = parts[3];
  const a =
    alphaPart === undefined
      ? 1
      : alphaPart.endsWith("%")
        ? parseFloat(alphaPart) / 100
        : parseFloat(alphaPart);
  const r = channel(parts[0]!);
  const g = channel(parts[1]!);
  const b = channel(parts[2]!);
  if ([r, g, b, a].some((n) => Number.isNaN(n))) return null;
  return { r, g, b, a };
}

export function toOpaqueHex(color: Rgba, backdrop: Rgba): string {
  const mix = (fg: number, bg: number) =>
    Math.round(fg * color.a + bg * (1 - color.a));
  const hex = (n: number) =>
    Math.max(0, Math.min(255, n)).toString(16).padStart(2, "0");
  return `#${hex(mix(color.r, backdrop.r))}${hex(
    mix(color.g, backdrop.g)
  )}${hex(mix(color.b, backdrop.b))}`;
}

export function buildMermaidTheme(
  read: TokenReader,
  options: { darkMode: boolean; fontFamily: string }
): MermaidThemeConfig {
  const canvas: Rgba = options.darkMode
    ? { r: 0, g: 0, b: 0, a: 1 }
    : { r: 255, g: 255, b: 255, a: 1 };
  const rawBackground = parseCssColor(read(MERMAID_THEME_TOKENS.background));
  const backdrop = rawBackground
    ? parseCssColor(toOpaqueHex(rawBackground, canvas)) ?? canvas
    : canvas;

  const themeVariables: Record<string, string | boolean> = {
    darkMode: options.darkMode,
    fontFamily: options.fontFamily,
    fontSize: "14px",
  };
  (Object.keys(MERMAID_THEME_TOKENS) as ThemeVariableName[]).forEach((name) => {
    const parsed = parseCssColor(read(MERMAID_THEME_TOKENS[name]));
    if (parsed) themeVariables[name] = toOpaqueHex(parsed, backdrop);
  });

  return {
    key: JSON.stringify(themeVariables),
    darkMode: options.darkMode,
    fontFamily: options.fontFamily,
    themeVariables,
  };
}

/** Used during SSR, where no stylesheet can be read. */
export const SERVER_MERMAID_THEME = buildMermaidTheme(() => "", {
  darkMode: false,
  fontFamily: DEFAULT_MERMAID_FONT_FAMILY,
});

/** Browser only: reads the tokens as currently applied to <html>. */
export function readDocumentTheme(
  doc: Document = document
): MermaidThemeConfig {
  const root = doc.documentElement;
  const view = doc.defaultView;
  const rootStyles = view?.getComputedStyle(root);
  const bodyStyles = doc.body ? view?.getComputedStyle(doc.body) : undefined;
  return buildMermaidTheme(
    (token) => rootStyles?.getPropertyValue(token).trim() ?? "",
    {
      darkMode: root.classList.contains("dark"),
      fontFamily: bodyStyles?.fontFamily || DEFAULT_MERMAID_FONT_FAMILY,
    }
  );
}

/**
 * Browser only: reads the tokens as applied to `element`, which may sit inside
 * a forced-light surface (`.theme-light`, the document panel's white page) on a
 * dark page. Without an element it falls back to `<html>`.
 */
export function readElementTheme(element: Element | null): MermaidThemeConfig {
  if (!element || typeof window === "undefined") return readDocumentTheme();
  const styles = window.getComputedStyle(element);
  const bodyStyles = document.body
    ? window.getComputedStyle(document.body)
    : undefined;
  return buildMermaidTheme((token) => styles.getPropertyValue(token).trim(), {
    darkMode:
      !element.closest(".theme-light") &&
      document.documentElement.classList.contains("dark"),
    fontFamily: bodyStyles?.fontFamily || DEFAULT_MERMAID_FONT_FAMILY,
  });
}
