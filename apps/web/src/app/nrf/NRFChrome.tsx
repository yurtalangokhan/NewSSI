"use client";

import { cn, ensureHrefProtocol } from "@/lib/utils";
import type { Components } from "react-markdown";
import Text from "@/refresh-components/texts/Text";
import IconButton from "@/refresh-components/buttons/IconButton";
import { SvgSidebar } from "@opal/icons";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { useAppSidebarContext } from "@/providers/AppSidebarProvider";
import useScreenSize from "@/hooks/useScreenSize";
import { buildAppFooterMarkdown } from "@/lib/appInfo";

const footerMarkdownComponents = {
  p: ({ children }: { children?: React.ReactNode }) => (
    <Text as="p" text03 secondaryAction className="!my-0 text-center">
      {children}
    </Text>
  ),
  a: ({
    href,
    className,
    children,
    ...rest
  }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => {
    const fullHref = ensureHrefProtocol(href);
    return (
      <a
        href={fullHref}
        target="_blank"
        rel="noopener noreferrer"
        {...rest}
        className={cn(className, "underline underline-offset-2")}
      >
        <Text text03 secondaryAction>
          {children}
        </Text>
      </a>
    );
  },
} satisfies Partial<Components>;

/**
 * Lightweight chrome overlay for the NRF page.
 *
 * Renders only the search/chat mode toggle (top-left) and footer (bottom),
 * absolutely positioned so they float transparently over NRFPage's own
 * background. This avoids pulling in the full AppLayouts.Root Header which
 * carries heavy state management (share/delete/move modals) that the
 * extension doesn't need.
 */
export default function NRFChrome() {
  const settings = useSettingsContext();
  const { isMobile } = useScreenSize();
  const { setFolded } = useAppSidebarContext();
  const customFooterContent =
    settings?.enterpriseSettings?.custom_lower_disclaimer_content ||
    buildAppFooterMarkdown(settings?.webVersion);

  const showHeader = isMobile;

  return (
    <>
      {/* Header chrome — top-left, mirrors position of settings button at top-right */}
      {showHeader && (
        <div className="absolute top-0 left-0 p-4 z-10 flex flex-row items-center gap-2">
          {isMobile && (
            <IconButton
              icon={SvgSidebar}
              onClick={() => setFolded(false)}
              internal
            />
          )}
        </div>
      )}

      {/* Footer — bottom-center, transparent background */}
      <footer className="absolute bottom-0 left-0 w-full z-10 flex flex-row justify-center items-center gap-2 px-2 pb-2 pointer-events-auto">
        <MinimalMarkdown
          content={customFooterContent}
          className="max-w-full text-center"
          components={footerMarkdownComponents}
        />
      </footer>
    </>
  );
}
