"use client";

import { useSettingsContext } from "@/providers/SettingsProvider";
import { LOGO_FOLDED_SIZE_PX, LOGO_UNFOLDED_SIZE_PX } from "@/lib/constants";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";
import Truncated from "@/refresh-components/texts/Truncated";
import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { appSettings } from "@/lib/settings";

export interface LogoProps {
  folded?: boolean;
  size?: number;
  className?: string;
}

const LOGO_CACHE_BUSTER = "v=20260505-2";

function TurksatMark({
  size,
  className,
  ariaLabel,
}: {
  size: number;
  className?: string;
  ariaLabel: string;
}) {
  return (
    <svg
      viewBox="0 0 48 48"
      aria-label={ariaLabel}
      role="img"
      className={cn("flex-shrink-0", className)}
      style={{ width: size, height: size }}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M19.1707 20.5314L28.3439 17.162L28.3439 39.0284L19.1707 42.3917V20.5314Z"
        fill="#009BDA"
      />
      <path
        d="M19.1707 10.4399V20.5314L0 12.1218V2.03033L19.1707 10.4399Z"
        fill="#009BDA"
      />
      <path
        d="M47.5146 15.4839V25.5754L28.3439 17.1657V7.07429L47.5146 15.4839Z"
        fill="#009BDA"
      />
    </svg>
  );
}

function TurksatWordmark({
  size,
  className,
  alt,
}: {
  size: number;
  className?: string;
  alt: string;
}) {
  const handleError = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (!img.src.includes("logo.turksat.black.svg")) {
      img.src = `/logo.turksat.black.svg?${LOGO_CACHE_BUSTER}`;
    }
  };

  // Render both light and dark variants with CSS-based switching (dark:hidden and hidden dark:block).
  // Because next-themes synchronously injects .dark on <html> before paint, CSS-based switching
  // applies on frame 0 without FOUC (flash of wrong theme logo) or hydration mismatch.
  return (
    <>
      <img
        src={`/logo.turksat.svg?${LOGO_CACHE_BUSTER}`}
        alt={alt}
        className={cn("flex-shrink-0 dark:hidden", className)}
        style={{ width: size, height: (size * 42) / 241 }}
        draggable={false}
        onError={handleError}
      />
      <img
        src={`/logo.turksat.white.svg?${LOGO_CACHE_BUSTER}`}
        alt={alt}
        className={cn("flex-shrink-0 hidden dark:block", className)}
        style={{ width: size, height: (size * 42) / 241 }}
        draggable={false}
        onError={handleError}
      />
    </>
  );
}

export default function Logo({ folded, size, className }: LogoProps) {
  const { t } = useTranslation("common", { keyPrefix: "common" });
  const foldedSize = size ?? LOGO_FOLDED_SIZE_PX;
  const unfoldedSize = size ?? LOGO_UNFOLDED_SIZE_PX;
  const settings = useSettingsContext();
  const logoDisplayStyle = settings.enterpriseSettings?.logo_display_style;
  const applicationName = settings.enterpriseSettings?.application_name;

  const logo = useMemo(
    () =>
      folded ? (
        <TurksatMark
          size={foldedSize}
          className={className}
          ariaLabel={t("turksatMarkAriaLabel")}
        />
      ) : (
        <TurksatWordmark
          size={unfoldedSize}
          className={className}
          alt={t("turksatLogoAlt")}
        />
      ),
    [className, folded, foldedSize, unfoldedSize, t]
  );

  const renderNameAndPoweredBy = (opts: {
    includeLogo: boolean;
    includeName: boolean;
  }) => {
    return (
      <div className="flex min-w-0 gap-2">
        {opts.includeLogo && logo}
        {!folded && (
          /* H3 text is 4px larger (28px) than the Logo icon (24px), so negative margin hack. */
          <div className="flex flex-1 flex-col -mt-0.5">
            {opts.includeName && (
              <Truncated headingH3>{applicationName}</Truncated>
            )}
            {!appSettings.NEXT_PUBLIC_DO_NOT_USE_TOGGLE_OFF_DANSWER_POWERED && (
              <Text
                secondaryBody
                text03
                className={"line-clamp-1 truncate"}
                nowrap
              >
                {t("poweredByAtlas")}
              </Text>
            )}
          </div>
        )}
      </div>
    );
  };

  // Handle "logo_only" display style
  if (logoDisplayStyle === "logo_only") {
    return renderNameAndPoweredBy({ includeLogo: true, includeName: false });
  }

  // Handle "name_only" display style
  if (logoDisplayStyle === "name_only") {
    return renderNameAndPoweredBy({ includeLogo: false, includeName: true });
  }

  // Handle "logo_and_name" or default behavior
  return applicationName
    ? renderNameAndPoweredBy({ includeLogo: true, includeName: true })
    : logo;
}
