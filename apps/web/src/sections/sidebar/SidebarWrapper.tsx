import React, { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@opal/components";
import { SvgSidebar } from "@opal/icons";
import { useTheme } from "next-themes";

interface LogoSectionProps {
  folded?: boolean;
  onFoldClick?: () => void;
}

const LOGO_CACHE_BUSTER = "v=20260505-2";

function LogoSection({ folded, onFoldClick }: LogoSectionProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const closeButton = useCallback(
    () => (
      <Button
        icon={SvgSidebar}
        prominence="tertiary"
        tooltip="Close Sidebar"
        onClick={onFoldClick}
      />
    ),
    [onFoldClick]
  );

  if (!mounted) {
    return (
      <div
        className={cn(
          "flex px-2.5 py-2 h-[3.25rem] min-h-[3.25rem] items-center",
          folded ? "justify-center" : "justify-between"
        )}
      >
        {!folded && <div className="h-8 w-[184px]" aria-hidden="true" />}
        {folded !== undefined && closeButton()}
      </div>
    );
  }

  const logoSrc =
    resolvedTheme === "light"
      ? `/logo.turksat.svg?${LOGO_CACHE_BUSTER}`
      : `/logo.turksat.white.svg?${LOGO_CACHE_BUSTER}`;

  return (
    <div
      className={cn(
        "flex px-2.5 py-2 h-[3.25rem] min-h-[3.25rem] items-center",
        folded ? "justify-center" : "justify-between"
      )}
    >
      {!folded && <img src={logoSrc} alt="Turksat Logo" className="h-8 w-auto" draggable={false} />}
      {folded !== undefined && closeButton()}
    </div>
  );
}

export interface SidebarWrapperProps {
  folded?: boolean;
  onFoldClick?: () => void;
  children?: React.ReactNode;
}

export default function SidebarWrapper({
  folded,
  onFoldClick,
  children,
}: SidebarWrapperProps) {
  return (
    // This extra `div` wrapping needs to be present (for some reason).
    // Without, the widths of the sidebars don't properly get set to the explicitly declared widths (i.e., `4rem` folded and `15rem` unfolded).
    <div>
      <div
        className={cn(
          "h-screen flex flex-col bg-background-tint-02 py-2 gap-4 group/SidebarWrapper transition-width duration-200 ease-in-out",
          folded ? "w-[3.25rem]" : "w-[15rem]"
        )}
      >
        <LogoSection folded={folded} onFoldClick={onFoldClick} />
        {children}
      </div>
    </div>
  );
}
