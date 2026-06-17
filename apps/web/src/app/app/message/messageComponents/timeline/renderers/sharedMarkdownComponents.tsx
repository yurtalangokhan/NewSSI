import type { Components } from "react-markdown";
import Text from "@/refresh-components/texts/Text";
import { useAppBackground } from "@/providers/AppBackgroundProvider";

function useForegroundMutedStyles() {
  return useAppBackground();
}

// Expanded view: normal spacing between paragraphs/lists
export const mutedTextMarkdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <Text
        as="p"
        text03
        mainUiMuted
        className={`!my-1 ${foregroundMutedTextClass}`}
        style={foregroundMutedTextStyle}
      >
        {children}
      </Text>
    );
  },
  li: ({ children }: { children?: React.ReactNode }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <Text
        as="li"
        text03
        mainUiMuted
        className={`!my-0 !py-0 leading-normal ${foregroundMutedTextClass}`}
        style={foregroundMutedTextStyle}
      >
        {children}
      </Text>
    );
  },
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="!pl-0 !ml-0 !my-0.5 list-inside">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="!pl-0 !ml-0 !my-0.5 list-inside">{children}</ol>
  ),
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <a
        href={href}
        className={`${foregroundMutedTextClass} mainUiMuted underline`}
        style={foregroundMutedTextStyle}
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    );
  },
} satisfies Partial<Components>;

// Collapsed view: no spacing for compact display
export const collapsedMarkdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <Text
        as="p"
        text03
        mainUiMuted
        className={`!my-0 ${foregroundMutedTextClass}`}
        style={foregroundMutedTextStyle}
      >
        {children}
      </Text>
    );
  },
  li: ({ children }: { children?: React.ReactNode }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <Text
        as="li"
        text03
        mainUiMuted
        className={`!my-0 !py-0 leading-normal ${foregroundMutedTextClass}`}
        style={foregroundMutedTextStyle}
      >
        {children}
      </Text>
    );
  },
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="!pl-0 !ml-0 !my-0 list-inside">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="!pl-0 !ml-0 !my-0 list-inside">{children}</ol>
  ),
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => {
    const { foregroundMutedTextClass, foregroundMutedTextStyle } =
      useForegroundMutedStyles();
    return (
      <a
        href={href}
        className={`${foregroundMutedTextClass} mainUiMuted underline`}
        style={foregroundMutedTextStyle}
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    );
  },
} satisfies Partial<Components>;
